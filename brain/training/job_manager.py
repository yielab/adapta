"""Training job management and queue"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import time

from brain.config import settings
from brain.training.models import (
    TrainingJob,
    TrainingConfig,
    TrainingStatus,
    JobState,
)

logger = logging.getLogger(__name__)


class JobManager:
    """Manages training jobs and queue"""

    def __init__(self):
        self.jobs_dir = settings.data_dir / "training_jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

        # In-memory job tracking
        self._jobs: Dict[str, TrainingJob] = {}
        self._job_lock = asyncio.Lock()

        # Load existing jobs
        self._load_jobs()

    def _load_jobs(self):
        """Load jobs from disk"""
        for job_file in self.jobs_dir.glob("**/job.json"):
            try:
                job = TrainingJob.load(job_file)
                self._jobs[job.job_id] = job
                logger.info(f"Loaded job {job.job_id} (state: {job.state.value})")
            except Exception as e:
                logger.error(f"Failed to load job from {job_file}: {e}")

    def _get_job_dir(self, job_id: str) -> Path:
        """Get directory for a specific job"""
        job_dir = self.jobs_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    async def create_job(
        self,
        agent_id: str,
        base_model: str,
        dataset_path: Path,
        adapter_name: str,
        config: TrainingConfig,
    ) -> TrainingJob:
        """Create a new training job"""
        async with self._job_lock:
            # Generate unique job ID
            job_id = f"job_{uuid.uuid4().hex[:12]}"

            # Create output directory
            job_dir = self._get_job_dir(job_id)
            output_dir = job_dir / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create adapter directory in agent's folder
            agent_adapter_dir = settings.agents_dir / agent_id / "adapters" / adapter_name
            agent_adapter_dir.mkdir(parents=True, exist_ok=True)

            # Create job
            job = TrainingJob(
                job_id=job_id,
                agent_id=agent_id,
                base_model=base_model,
                dataset_path=dataset_path,
                adapter_name=adapter_name,
                config=config,
                output_dir=output_dir,
                adapter_path=agent_adapter_dir,
            )

            # Save job
            job.save(job_dir / "job.json")

            # Store in memory
            self._jobs[job_id] = job

            logger.info(
                f"Created training job {job_id} for agent {agent_id} "
                f"(model: {base_model}, adapter: {adapter_name})"
            )

            return job

    async def get_job(self, job_id: str) -> Optional[TrainingJob]:
        """Get a job by ID"""
        return self._jobs.get(job_id)

    async def list_jobs(
        self,
        agent_id: Optional[str] = None,
        state: Optional[JobState] = None,
    ) -> List[TrainingJob]:
        """List jobs with optional filters"""
        jobs = list(self._jobs.values())

        if agent_id:
            jobs = [j for j in jobs if j.agent_id == agent_id]

        if state:
            jobs = [j for j in jobs if j.state == state]

        # Sort by created_at (newest first)
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return jobs

    async def update_job_state(
        self,
        job_id: str,
        state: JobState,
        error_message: Optional[str] = None,
        error_traceback: Optional[str] = None,
    ):
        """Update job state"""
        async with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                logger.warning(f"Job {job_id} not found for state update")
                return

            job.state = state

            # Update timestamps
            if state == JobState.TRAINING and not job.started_at:
                job.started_at = time.time()
            elif state in [JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED]:
                job.completed_at = time.time()

            # Update error info
            if error_message:
                job.error_message = error_message
            if error_traceback:
                job.error_traceback = error_traceback

            # Update progress
            if state == JobState.COMPLETED:
                job.progress = 1.0
            elif state in [JobState.FAILED, JobState.CANCELLED]:
                # Keep current progress
                pass

            # Save job
            job_dir = self._get_job_dir(job_id)
            job.save(job_dir / "job.json")

            logger.info(f"Job {job_id} state updated to {state.value}")

    async def get_job_status(self, job_id: str) -> Optional[TrainingStatus]:
        """Get current status of a job"""
        job = self._jobs.get(job_id)
        if not job:
            return None

        return job.get_status()

    async def cancel_job(self, job_id: str) -> bool:
        """Cancel a training job"""
        job = self._jobs.get(job_id)
        if not job:
            logger.warning(f"Job {job_id} not found for cancellation")
            return False

        if job.state.is_finished:
            logger.warning(f"Job {job_id} already finished, cannot cancel")
            return False

        await self.update_job_state(job_id, JobState.CANCELLED)

        # Set cancellation flag that trainer will check
        job.metadata["cancel_requested"] = True

        # If a process is running, attempt to terminate it gracefully
        if "process_pid" in job.metadata:
            try:
                import os
                import signal
                pid = job.metadata["process_pid"]
                os.kill(pid, signal.SIGTERM)
                logger.info(f"Sent termination signal to process {pid}")
            except (ProcessLookupError, PermissionError) as e:
                logger.warning(f"Could not terminate process: {e}")

        logger.info(f"Cancelled job {job_id}")
        return True

    async def delete_job(self, job_id: str) -> bool:
        """Delete a job and its files"""
        async with self._job_lock:
            job = self._jobs.get(job_id)
            if not job:
                return False

            # Delete job directory
            job_dir = self._get_job_dir(job_id)
            if job_dir.exists():
                import shutil

                shutil.rmtree(job_dir)

            # Remove from memory
            del self._jobs[job_id]

            logger.info(f"Deleted job {job_id}")
            return True

    async def cleanup_old_jobs(self, days: int = 30):
        """Clean up completed jobs older than specified days"""
        cutoff_time = time.time() - (days * 24 * 60 * 60)

        jobs_to_delete = []
        for job_id, job in self._jobs.items():
            if (
                job.state.is_finished
                and job.completed_at
                and job.completed_at < cutoff_time
            ):
                jobs_to_delete.append(job_id)

        for job_id in jobs_to_delete:
            await self.delete_job(job_id)

        if jobs_to_delete:
            logger.info(f"Cleaned up {len(jobs_to_delete)} old jobs")

    def get_queue_status(self) -> Dict:
        """Get overall queue status"""
        queued = len([j for j in self._jobs.values() if j.state == JobState.QUEUED])
        running = len(
            [
                j
                for j in self._jobs.values()
                if j.state in [JobState.PREPARING, JobState.TRAINING, JobState.EVALUATING]
            ]
        )
        completed = len([j for j in self._jobs.values() if j.state == JobState.COMPLETED])
        failed = len([j for j in self._jobs.values() if j.state == JobState.FAILED])
        cancelled = len([j for j in self._jobs.values() if j.state == JobState.CANCELLED])

        return {
            "total_jobs": len(self._jobs),
            "queued": queued,
            "running": running,
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
        }


# Global instance
job_manager = JobManager()
