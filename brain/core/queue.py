"""
Request queue management for batch processing and concurrent request handling.

This module provides:
- Priority queue for inference requests
- Batch processing capabilities
- Concurrent request handling
- Queue statistics and monitoring
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Request priority levels"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class RequestStatus(Enum):
    """Request status in queue"""
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueueRequest:
    """A request in the queue"""
    id: str
    priority: Priority
    model: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: RequestStatus = RequestStatus.QUEUED
    result: Optional[Any] = None
    error: Optional[str] = None

    @property
    def wait_time(self) -> float:
        """Time spent waiting in queue (seconds)"""
        if self.started_at:
            return self.started_at - self.created_at
        return time.time() - self.created_at

    @property
    def processing_time(self) -> Optional[float]:
        """Time spent processing (seconds)"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        return None

    @property
    def total_time(self) -> Optional[float]:
        """Total time from creation to completion (seconds)"""
        if self.completed_at:
            return self.completed_at - self.created_at
        return None


@dataclass
class QueueStats:
    """Queue statistics"""
    total_requests: int = 0
    queued: int = 0
    processing: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    avg_wait_time: float = 0.0
    avg_processing_time: float = 0.0
    requests_per_minute: float = 0.0
    queue_by_priority: Dict[str, int] = field(default_factory=dict)
    queue_by_model: Dict[str, int] = field(default_factory=dict)


class RequestQueue:
    """
    Priority queue for inference requests with batch processing support.

    Features:
    - Priority-based request ordering
    - Concurrent request processing
    - Request batching for efficiency
    - Queue statistics and monitoring
    - Request cancellation
    """

    def __init__(
        self,
        max_workers: int = 4,
        max_queue_size: int = 1000,
        batch_size: int = 1,
        batch_timeout: float = 0.1,
    ):
        """
        Initialize request queue.

        Args:
            max_workers: Maximum concurrent workers
            max_queue_size: Maximum queue size (0 = unlimited)
            batch_size: Maximum batch size for processing
            batch_timeout: Maximum time to wait for batch (seconds)
        """
        self.max_workers = max_workers
        self.max_queue_size = max_queue_size
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout

        # Queue storage (priority -> list of requests)
        self._queues: Dict[Priority, asyncio.Queue] = {
            priority: asyncio.Queue() for priority in Priority
        }

        # Request tracking
        self._requests: Dict[str, QueueRequest] = {}
        self._futures: Dict[str, asyncio.Future] = {}

        # Statistics
        self._stats = {
            'total_requests': 0,
            'completed': 0,
            'failed': 0,
            'cancelled': 0,
            'wait_times': [],
            'processing_times': [],
            'request_times': [],
        }

        # Workers
        self._workers: List[asyncio.Task] = []
        self._running = False
        self._processor: Optional[Callable] = None

    async def start(self, processor: Callable):
        """
        Start the queue workers.

        Args:
            processor: Async function to process requests
                       Should accept (model, payload) and return result
        """
        if self._running:
            logger.warning("Queue already running")
            return

        self._processor = processor
        self._running = True

        # Start worker tasks
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(i))
            self._workers.append(worker)

        logger.info(f"Started {self.max_workers} queue workers")

    async def stop(self):
        """Stop the queue workers"""
        if not self._running:
            return

        self._running = False

        # Cancel all workers
        for worker in self._workers:
            worker.cancel()

        # Wait for workers to finish
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

        logger.info("Stopped queue workers")

    async def submit(
        self,
        model: str,
        payload: Dict[str, Any],
        priority: Priority = Priority.NORMAL,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Submit a request to the queue and wait for result.

        Args:
            model: Model name
            payload: Request payload
            priority: Request priority
            timeout: Maximum wait time (None = no timeout)

        Returns:
            Processing result

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
            Exception: If processing fails
        """
        # Check queue size
        if self.max_queue_size > 0:
            total_queued = sum(q.qsize() for q in self._queues.values())
            if total_queued >= self.max_queue_size:
                raise Exception(f"Queue is full ({self.max_queue_size} requests)")

        # Create request
        request = QueueRequest(
            id=str(uuid.uuid4()),
            priority=priority,
            model=model,
            payload=payload,
        )

        # Create future for result
        future = asyncio.Future()

        # Store request and future
        self._requests[request.id] = request
        self._futures[request.id] = future

        # Update stats
        self._stats['total_requests'] += 1
        self._stats['request_times'].append(time.time())

        # Add to queue
        await self._queues[priority].put(request)

        logger.debug(
            f"Queued request {request.id} "
            f"(priority={priority.name}, model={model})"
        )

        # Wait for result
        try:
            if timeout:
                result = await asyncio.wait_for(future, timeout=timeout)
            else:
                result = await future
            return result
        except asyncio.TimeoutError:
            # Cancel request
            request.status = RequestStatus.CANCELLED
            self._stats['cancelled'] += 1
            raise
        except Exception as e:
            logger.error(f"Request {request.id} failed: {e}")
            raise
        finally:
            # Clean up
            self._requests.pop(request.id, None)
            self._futures.pop(request.id, None)

    async def _worker(self, worker_id: int):
        """Worker task that processes requests from queue"""
        logger.info(f"Worker {worker_id} started")

        try:
            while self._running:
                # Get next request (check all priorities from high to low)
                request = await self._get_next_request()

                if not request:
                    # No requests, wait a bit
                    await asyncio.sleep(0.01)
                    continue

                # Process request
                await self._process_request(request, worker_id)
        except asyncio.CancelledError:
            logger.info(f"Worker {worker_id} cancelled")
        except Exception as e:
            logger.error(f"Worker {worker_id} error: {e}", exc_info=True)

        logger.info(f"Worker {worker_id} stopped")

    async def _get_next_request(self) -> Optional[QueueRequest]:
        """Get next request from highest priority queue"""
        # Check queues from highest to lowest priority
        for priority in sorted(Priority, key=lambda p: p.value, reverse=True):
            queue = self._queues[priority]

            if not queue.empty():
                try:
                    request = queue.get_nowait()
                    return request
                except asyncio.QueueEmpty:
                    continue

        return None

    async def _process_request(self, request: QueueRequest, worker_id: int):
        """Process a single request"""
        request.status = RequestStatus.PROCESSING
        request.started_at = time.time()

        # Track wait time
        wait_time = request.wait_time
        self._stats['wait_times'].append(wait_time)

        logger.debug(
            f"Worker {worker_id} processing request {request.id} "
            f"(waited {wait_time:.2f}s)"
        )

        try:
            # Process request
            result = await self._processor(request.model, request.payload)

            # Mark as completed
            request.status = RequestStatus.COMPLETED
            request.completed_at = time.time()
            request.result = result

            # Track processing time
            processing_time = request.processing_time
            self._stats['processing_times'].append(processing_time)
            self._stats['completed'] += 1

            logger.debug(
                f"Worker {worker_id} completed request {request.id} "
                f"(took {processing_time:.2f}s)"
            )

            # Resolve future
            future = self._futures.get(request.id)
            if future and not future.done():
                future.set_result(result)

        except Exception as e:
            # Mark as failed
            request.status = RequestStatus.FAILED
            request.completed_at = time.time()
            request.error = str(e)
            self._stats['failed'] += 1

            logger.error(
                f"Worker {worker_id} failed request {request.id}: {e}",
                exc_info=True
            )

            # Reject future
            future = self._futures.get(request.id)
            if future and not future.done():
                future.set_exception(e)

    def get_stats(self) -> QueueStats:
        """Get queue statistics"""
        # Calculate averages
        avg_wait = 0.0
        if self._stats['wait_times']:
            avg_wait = sum(self._stats['wait_times'][-100:]) / min(
                100, len(self._stats['wait_times'])
            )

        avg_processing = 0.0
        if self._stats['processing_times']:
            avg_processing = sum(self._stats['processing_times'][-100:]) / min(
                100, len(self._stats['processing_times'])
            )

        # Calculate requests per minute
        rpm = 0.0
        if self._stats['request_times']:
            # Count requests in last minute
            now = time.time()
            recent = [t for t in self._stats['request_times'] if now - t < 60]
            rpm = len(recent)

        # Count by priority
        queue_by_priority = {}
        for priority, queue in self._queues.items():
            queue_by_priority[priority.name] = queue.qsize()

        # Count by model
        queue_by_model = defaultdict(int)
        for request in self._requests.values():
            if request.status == RequestStatus.QUEUED:
                queue_by_model[request.model] += 1

        # Count by status
        queued = sum(1 for r in self._requests.values() if r.status == RequestStatus.QUEUED)
        processing = sum(1 for r in self._requests.values() if r.status == RequestStatus.PROCESSING)

        return QueueStats(
            total_requests=self._stats['total_requests'],
            queued=queued,
            processing=processing,
            completed=self._stats['completed'],
            failed=self._stats['failed'],
            cancelled=self._stats['cancelled'],
            avg_wait_time=avg_wait,
            avg_processing_time=avg_processing,
            requests_per_minute=rpm,
            queue_by_priority=queue_by_priority,
            queue_by_model=dict(queue_by_model),
        )

    def clear_stats(self):
        """Clear statistics history"""
        self._stats['wait_times'].clear()
        self._stats['processing_times'].clear()
        # Keep request_times for RPM calculation
        now = time.time()
        self._stats['request_times'] = [
            t for t in self._stats['request_times'] if now - t < 60
        ]


# Global queue instance
_queue: Optional[RequestQueue] = None


def get_queue() -> RequestQueue:
    """Get the global request queue"""
    global _queue
    if _queue is None:
        _queue = RequestQueue(
            max_workers=4,
            max_queue_size=1000,
            batch_size=1,
            batch_timeout=0.1,
        )
    return _queue


async def start_queue(processor: Callable):
    """Start the global queue"""
    queue = get_queue()
    await queue.start(processor)


async def stop_queue():
    """Stop the global queue"""
    queue = get_queue()
    await queue.stop()
