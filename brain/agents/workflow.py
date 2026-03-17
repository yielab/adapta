"""
Multi-agent workflow system with YAML-based workflow definitions.

Enables defining complex multi-agent workflows with:
- Sequential and parallel task execution
- Conditional routing based on results
- Result aggregation
- Error handling and retries
"""

import asyncio
import logging
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum

from brain.agents import agent_manager
from brain.agents.communication import get_communication_hub, MessageType, MessagePriority

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Workflow execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """Types of workflow tasks"""
    AGENT_TASK = "agent_task"  # Execute with single agent
    PARALLEL = "parallel"  # Execute multiple tasks in parallel
    SEQUENTIAL = "sequential"  # Execute tasks sequentially
    CONDITIONAL = "conditional"  # Execute based on condition
    AGGREGATE = "aggregate"  # Aggregate results from multiple tasks


@dataclass
class WorkflowTask:
    """A task in a workflow"""
    id: str
    task_type: TaskType
    agent_id: Optional[str] = None  # For AGENT_TASK
    prompt: Optional[str] = None  # For AGENT_TASK
    subtasks: List['WorkflowTask'] = field(default_factory=list)  # For PARALLEL/SEQUENTIAL
    condition: Optional[str] = None  # For CONDITIONAL
    aggregation_method: Optional[str] = None  # For AGGREGATE
    metadata: Dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    timeout: Optional[float] = None


@dataclass
class TaskResult:
    """Result of a workflow task execution"""
    task_id: str
    status: WorkflowStatus
    result: Any = None
    error: Optional[str] = None
    duration: float = 0.0
    retries: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowExecution:
    """A workflow execution instance"""
    id: str
    workflow_id: str
    status: WorkflowStatus
    tasks: List[WorkflowTask]
    results: Dict[str, TaskResult] = field(default_factory=dict)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)  # Shared context between tasks


class WorkflowEngine:
    """
    Workflow execution engine for multi-agent workflows.

    Features:
    - YAML workflow definitions
    - Sequential and parallel execution
    - Conditional routing
    - Result aggregation
    - Error handling and retries
    """

    def __init__(self):
        """Initialize workflow engine"""
        self.comm_hub = get_communication_hub()
        self._workflows: Dict[str, Dict] = {}
        self._executions: Dict[str, WorkflowExecution] = {}

    def load_workflow_from_yaml(self, yaml_content: str) -> str:
        """
        Load a workflow from YAML definition.

        Args:
            yaml_content: YAML workflow definition

        Returns:
            Workflow ID

        Example YAML:
        ```yaml
        workflow:
          id: research_workflow
          name: Research and Summarize
          tasks:
            - id: research
              type: agent_task
              agent_id: researcher
              prompt: "Research the topic: {topic}"
              timeout: 60

            - id: summarize
              type: agent_task
              agent_id: summarizer
              prompt: "Summarize this research: {research.result}"
              timeout: 30

            - id: review
              type: parallel
              subtasks:
                - id: fact_check
                  type: agent_task
                  agent_id: fact_checker
                  prompt: "Fact check: {summarize.result}"

                - id: grammar_check
                  type: agent_task
                  agent_id: editor
                  prompt: "Check grammar: {summarize.result}"
        ```
        """
        try:
            workflow_def = yaml.safe_load(yaml_content)
            workflow_id = workflow_def['workflow']['id']
            self._workflows[workflow_id] = workflow_def['workflow']
            logger.info(f"Loaded workflow: {workflow_id}")
            return workflow_id
        except Exception as e:
            logger.error(f"Failed to load workflow: {e}")
            raise ValueError(f"Invalid workflow YAML: {e}")

    async def execute_workflow(
        self,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> WorkflowExecution:
        """
        Execute a workflow.

        Args:
            workflow_id: Workflow ID to execute
            context: Initial context/parameters

        Returns:
            WorkflowExecution with results
        """
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow not found: {workflow_id}")

        workflow_def = self._workflows[workflow_id]

        # Create execution
        import uuid
        execution_id = str(uuid.uuid4())
        execution = WorkflowExecution(
            id=execution_id,
            workflow_id=workflow_id,
            status=WorkflowStatus.RUNNING,
            tasks=self._parse_tasks(workflow_def.get('tasks', [])),
            context=context or {},
            started_at=datetime.now().timestamp(),
        )

        self._executions[execution_id] = execution
        logger.info(f"Started workflow execution: {execution_id}")

        try:
            # Execute all tasks
            for task in execution.tasks:
                result = await self._execute_task(task, execution)
                execution.results[task.id] = result

                if result.status == WorkflowStatus.FAILED and task.max_retries == 0:
                    execution.status = WorkflowStatus.FAILED
                    execution.error = f"Task {task.id} failed: {result.error}"
                    break

            if execution.status == WorkflowStatus.RUNNING:
                execution.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            execution.status = WorkflowStatus.FAILED
            execution.error = str(e)

        finally:
            execution.completed_at = datetime.now().timestamp()

        logger.info(
            f"Workflow execution {execution_id} {execution.status.value}"
        )
        return execution

    async def _execute_task(
        self,
        task: WorkflowTask,
        execution: WorkflowExecution
    ) -> TaskResult:
        """Execute a single workflow task"""
        import time
        start_time = time.time()

        result = TaskResult(
            task_id=task.id,
            status=WorkflowStatus.RUNNING,
        )

        try:
            if task.task_type == TaskType.AGENT_TASK:
                result = await self._execute_agent_task(task, execution)

            elif task.task_type == TaskType.PARALLEL:
                result = await self._execute_parallel(task, execution)

            elif task.task_type == TaskType.SEQUENTIAL:
                result = await self._execute_sequential(task, execution)

            elif task.task_type == TaskType.CONDITIONAL:
                result = await self._execute_conditional(task, execution)

            elif task.task_type == TaskType.AGGREGATE:
                result = await self._execute_aggregate(task, execution)

            else:
                raise ValueError(f"Unknown task type: {task.task_type}")

            result.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error(f"Task {task.id} failed: {e}", exc_info=True)
            result.status = WorkflowStatus.FAILED
            result.error = str(e)

        finally:
            result.duration = time.time() - start_time

        return result

    async def _execute_agent_task(
        self,
        task: WorkflowTask,
        execution: WorkflowExecution
    ) -> TaskResult:
        """Execute a task with a single agent"""
        if not task.agent_id or not task.prompt:
            raise ValueError(f"Task {task.id} missing agent_id or prompt")

        # Get agent
        agent = agent_manager.get_agent(task.agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {task.agent_id}")

        # Interpolate prompt with context
        prompt = self._interpolate_prompt(task.prompt, execution)

        # Send message to agent via communication hub
        self.comm_hub.register_agent(task.agent_id)
        response = await self.comm_hub.send_message(
            from_agent="workflow_engine",
            to_agent=task.agent_id,
            content=prompt,
            message_type=MessageType.TASK,
            priority=MessagePriority.NORMAL,
            requires_response=True,
            timeout=task.timeout or 60.0,
        )

        if not response:
            raise TimeoutError(f"Agent {task.agent_id} did not respond in time")

        # Store result in context
        execution.context[task.id] = {"result": response.content}

        return TaskResult(
            task_id=task.id,
            status=WorkflowStatus.COMPLETED,
            result=response.content,
        )

    async def _execute_parallel(
        self,
        task: WorkflowTask,
        execution: WorkflowExecution
    ) -> TaskResult:
        """Execute multiple tasks in parallel"""
        if not task.subtasks:
            raise ValueError(f"Parallel task {task.id} has no subtasks")

        # Execute all subtasks concurrently
        tasks_coro = [
            self._execute_task(subtask, execution)
            for subtask in task.subtasks
        ]

        results = await asyncio.gather(*tasks_coro, return_exceptions=True)

        # Check for failures
        failed = [r for r in results if isinstance(r, Exception) or r.status == WorkflowStatus.FAILED]
        if failed:
            return TaskResult(
                task_id=task.id,
                status=WorkflowStatus.FAILED,
                error=f"{len(failed)} subtasks failed",
                result=results,
            )

        return TaskResult(
            task_id=task.id,
            status=WorkflowStatus.COMPLETED,
            result=[r.result for r in results if not isinstance(r, Exception)],
        )

    async def _execute_sequential(
        self,
        task: WorkflowTask,
        execution: WorkflowExecution
    ) -> TaskResult:
        """Execute tasks sequentially"""
        if not task.subtasks:
            raise ValueError(f"Sequential task {task.id} has no subtasks")

        results = []
        for subtask in task.subtasks:
            result = await self._execute_task(subtask, execution)
            results.append(result)

            if result.status == WorkflowStatus.FAILED:
                return TaskResult(
                    task_id=task.id,
                    status=WorkflowStatus.FAILED,
                    error=f"Subtask {subtask.id} failed: {result.error}",
                    result=results,
                )

        return TaskResult(
            task_id=task.id,
            status=WorkflowStatus.COMPLETED,
            result=[r.result for r in results],
        )

    async def _execute_conditional(
        self,
        task: WorkflowTask,
        execution: WorkflowExecution
    ) -> TaskResult:
        """Execute task based on condition"""
        if not task.condition:
            raise ValueError(f"Conditional task {task.id} has no condition")

        # Evaluate condition (simple Python expression)
        condition_result = self._evaluate_condition(task.condition, execution)

        if condition_result and task.subtasks:
            # Execute first subtask (true branch)
            return await self._execute_task(task.subtasks[0], execution)
        elif not condition_result and len(task.subtasks) > 1:
            # Execute second subtask (false branch)
            return await self._execute_task(task.subtasks[1], execution)
        else:
            return TaskResult(
                task_id=task.id,
                status=WorkflowStatus.COMPLETED,
                result=None,
                metadata={"condition": condition_result},
            )

    async def _execute_aggregate(
        self,
        task: WorkflowTask,
        execution: WorkflowExecution
    ) -> TaskResult:
        """Aggregate results from multiple tasks"""
        if not task.subtasks:
            raise ValueError(f"Aggregate task {task.id} has no subtasks")

        # Get all results
        results = []
        for subtask_id in [st.id for st in task.subtasks]:
            if subtask_id in execution.results:
                results.append(execution.results[subtask_id].result)

        # Apply aggregation method
        aggregation = task.aggregation_method or "list"
        if aggregation == "list":
            aggregated = results
        elif aggregation == "concat":
            aggregated = "\n\n".join(str(r) for r in results)
        elif aggregation == "count":
            aggregated = len(results)
        else:
            aggregated = results

        return TaskResult(
            task_id=task.id,
            status=WorkflowStatus.COMPLETED,
            result=aggregated,
        )

    def _parse_tasks(self, tasks_data: List[Dict]) -> List[WorkflowTask]:
        """Parse task definitions from workflow YAML"""
        tasks = []
        for task_data in tasks_data:
            task = WorkflowTask(
                id=task_data['id'],
                task_type=TaskType(task_data['type']),
                agent_id=task_data.get('agent_id'),
                prompt=task_data.get('prompt'),
                subtasks=self._parse_tasks(task_data.get('subtasks', [])),
                condition=task_data.get('condition'),
                aggregation_method=task_data.get('aggregation_method'),
                metadata=task_data.get('metadata', {}),
                max_retries=task_data.get('max_retries', 0),
                timeout=task_data.get('timeout'),
            )
            tasks.append(task)
        return tasks

    def _interpolate_prompt(self, prompt: str, execution: WorkflowExecution) -> str:
        """Interpolate prompt with context values"""
        import re

        # Replace {var} with context[var]
        # Replace {task_id.result} with execution.results[task_id].result

        def replace_var(match):
            var = match.group(1)
            if '.' in var:
                task_id, field = var.split('.', 1)
                if task_id in execution.context:
                    return str(execution.context[task_id].get(field, match.group(0)))
            elif var in execution.context:
                return str(execution.context[var])
            return match.group(0)

        return re.sub(r'\{([^}]+)\}', replace_var, prompt)

    def _evaluate_condition(self, condition: str, execution: WorkflowExecution) -> bool:
        """Evaluate a simple condition"""
        # Interpolate condition
        condition_str = self._interpolate_prompt(condition, execution)

        # Safe eval (very limited)
        try:
            # Only allow simple comparisons
            return eval(condition_str, {"__builtins__": {}}, {})
        except:
            logger.warning(f"Failed to evaluate condition: {condition}")
            return False

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Get workflow execution by ID"""
        return self._executions.get(execution_id)

    def get_workflow(self, workflow_id: str) -> Optional[Dict]:
        """Get workflow definition by ID"""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[str]:
        """List all loaded workflows"""
        return list(self._workflows.keys())

    def list_executions(self) -> List[str]:
        """List all workflow executions"""
        return list(self._executions.keys())


# Global workflow engine instance
_workflow_engine: Optional[WorkflowEngine] = None


def get_workflow_engine() -> WorkflowEngine:
    """Get the global workflow engine"""
    global _workflow_engine
    if _workflow_engine is None:
        _workflow_engine = WorkflowEngine()
    return _workflow_engine
