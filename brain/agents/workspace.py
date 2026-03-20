"""
Agent Workspace - Persistent note-taking and artifact management.

Based on Anthropic's recommendation for structured note-taking to maintain
context across long-horizon tasks.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class Note:
    """A structured note in the agent's workspace."""
    content: str
    filename: str
    created_at: datetime
    updated_at: datetime
    category: Optional[str] = None
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "filename": self.filename,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "category": self.category,
            "importance": self.importance,
            "metadata": self.metadata
        }


class AgentWorkspace:
    """
    Persistent workspace for agent notes and artifacts.

    Implements Anthropic's structured note-taking pattern for maintaining
    context across sessions and long-running tasks.
    """

    def __init__(self, agent_id: str, base_dir: str = ".brain/workspaces"):
        """
        Initialize agent workspace.

        Args:
            agent_id: Unique agent identifier
            base_dir: Base directory for all workspaces
        """
        self.agent_id = agent_id
        self.base_dir = Path(base_dir)
        self.workspace_dir = self.base_dir / agent_id

        # Create workspace directory
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Special files
        self.notes_file = self.workspace_dir / "NOTES.md"
        self.summary_file = self.workspace_dir / "SUMMARY.md"
        self.decisions_file = self.workspace_dir / "DECISIONS.md"
        self.tasks_file = self.workspace_dir / "TASKS.md"
        self.context_file = self.workspace_dir / "CONTEXT.json"

        # Initialize special files if needed
        self._init_special_files()

        logger.info(f"Initialized workspace for agent {agent_id} at {self.workspace_dir}")

    def _init_special_files(self):
        """Initialize special workspace files."""
        # Main notes file
        if not self.notes_file.exists():
            self.notes_file.write_text(
                f"# Agent Notes - {self.agent_id}\n\n"
                f"Created: {datetime.now().isoformat()}\n\n"
                "## Session Notes\n\n"
            )

        # Summary file
        if not self.summary_file.exists():
            self.summary_file.write_text(
                f"# Agent Summary - {self.agent_id}\n\n"
                "## Current State\n\n"
                "## Key Decisions\n\n"
                "## Important Context\n\n"
            )

        # Decisions log
        if not self.decisions_file.exists():
            self.decisions_file.write_text(
                f"# Decision Log - {self.agent_id}\n\n"
                "## Architectural Decisions\n\n"
            )

        # Tasks tracking
        if not self.tasks_file.exists():
            self.tasks_file.write_text(
                f"# Task Tracking - {self.agent_id}\n\n"
                "## In Progress\n\n"
                "## Completed\n\n"
                "## Blocked\n\n"
            )

    def write_note(
        self,
        content: str,
        filename: str = "NOTES.md",
        category: Optional[str] = None,
        importance: float = 0.5,
        append: bool = True
    ) -> Note:
        """
        Write a note to the workspace.

        Args:
            content: Note content
            filename: File to write to
            category: Note category
            importance: Importance score (0-1)
            append: Whether to append or overwrite

        Returns:
            Created Note object
        """
        file_path = self.workspace_dir / filename

        # Add timestamp and formatting
        timestamp = datetime.now().isoformat()
        formatted_content = f"\n---\n*[{timestamp}]*\n{content}\n"

        # Write to file
        if append and file_path.exists():
            current = file_path.read_text()
            file_path.write_text(current + formatted_content)
        else:
            file_path.write_text(formatted_content)

        # Create Note object
        note = Note(
            content=content,
            filename=filename,
            created_at=datetime.now(),
            updated_at=datetime.now(),
            category=category,
            importance=importance
        )

        logger.debug(f"Wrote note to {filename} for agent {self.agent_id}")
        return note

    def read_notes(self, filename: Optional[str] = None) -> Dict[str, str]:
        """
        Read notes from workspace.

        Args:
            filename: Specific file to read (None for all)

        Returns:
            Dictionary of filename -> content
        """
        notes = {}

        if filename:
            file_path = self.workspace_dir / filename
            if file_path.exists():
                notes[filename] = file_path.read_text()
        else:
            # Read all markdown files
            for file_path in self.workspace_dir.glob("*.md"):
                notes[file_path.name] = file_path.read_text()

        return notes

    def append_decision(self, decision: str, rationale: str):
        """
        Log an architectural decision.

        Args:
            decision: The decision made
            rationale: Why this decision was made
        """
        content = (
            f"\n## Decision: {decision}\n"
            f"**Date**: {datetime.now().isoformat()}\n"
            f"**Rationale**: {rationale}\n"
        )

        self.write_note(
            content=content,
            filename="DECISIONS.md",
            category="decision",
            importance=0.8,
            append=True
        )

    def update_summary(self, section: str, content: str):
        """
        Update a section in the summary file.

        Args:
            section: Section to update (e.g., "Current State")
            content: New content for the section
        """
        summary_text = self.summary_file.read_text()

        # Find and replace section
        import re
        pattern = f"## {section}.*?(?=##|$)"
        replacement = f"## {section}\n\n{content}\n\n"

        new_summary = re.sub(pattern, replacement, summary_text, flags=re.DOTALL)

        # If section doesn't exist, append it
        if f"## {section}" not in summary_text:
            new_summary += f"\n## {section}\n\n{content}\n\n"

        self.summary_file.write_text(new_summary)
        logger.debug(f"Updated summary section '{section}' for agent {self.agent_id}")

    def track_task(self, task: str, status: str = "in_progress"):
        """
        Track a task in the workspace.

        Args:
            task: Task description
            status: Task status (in_progress/completed/blocked)
        """
        tasks_text = self.tasks_file.read_text()

        # Add task to appropriate section
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        task_entry = f"- [{timestamp}] {task}\n"

        if status == "in_progress":
            section = "## In Progress"
        elif status == "completed":
            section = "## Completed"
        elif status == "blocked":
            section = "## Blocked"
        else:
            section = "## Other"

        # Find section and append
        if section in tasks_text:
            lines = tasks_text.split('\n')
            for i, line in enumerate(lines):
                if line == section:
                    # Insert after section header
                    lines.insert(i + 2, task_entry.rstrip())
                    break
            tasks_text = '\n'.join(lines)
        else:
            # Add section
            tasks_text += f"\n{section}\n\n{task_entry}"

        self.tasks_file.write_text(tasks_text)

    def save_context(self, context: Dict[str, Any]):
        """
        Save important context for persistence.

        Args:
            context: Context dictionary to save
        """
        # Load existing context
        if self.context_file.exists():
            existing = json.loads(self.context_file.read_text())
        else:
            existing = {}

        # Merge with new context
        existing.update(context)
        existing["last_updated"] = datetime.now().isoformat()

        # Save
        self.context_file.write_text(json.dumps(existing, indent=2))

    def load_context(self) -> Dict[str, Any]:
        """
        Load saved context.

        Returns:
            Saved context dictionary
        """
        if self.context_file.exists():
            return json.loads(self.context_file.read_text())
        return {}

    def get_relevant_notes(
        self,
        query: str,
        max_notes: int = 5,
        min_importance: float = 0.3
    ) -> List[str]:
        """
        Get notes relevant to a query.

        Args:
            query: Query string
            max_notes: Maximum number of notes to return
            min_importance: Minimum importance threshold

        Returns:
            List of relevant note contents
        """
        relevant = []
        query_lower = query.lower()

        # Search through all notes
        for filename, content in self.read_notes().items():
            # Simple relevance scoring based on keyword matching
            score = 0
            content_lower = content.lower()

            # Check for query words
            for word in query_lower.split():
                if word in content_lower:
                    score += content_lower.count(word)

            if score > 0:
                relevant.append((score, content[:500]))  # Keep first 500 chars

        # Sort by relevance and return top N
        relevant.sort(key=lambda x: x[0], reverse=True)
        return [content for _, content in relevant[:max_notes]]

    def create_session_checkpoint(self) -> str:
        """
        Create a checkpoint of the current session.

        Returns:
            Checkpoint ID
        """
        checkpoint_id = hashlib.md5(
            f"{self.agent_id}:{datetime.now().isoformat()}".encode()
        ).hexdigest()[:8]

        checkpoint_dir = self.workspace_dir / "checkpoints" / checkpoint_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)

        # Copy current state
        import shutil
        for file_path in self.workspace_dir.glob("*.md"):
            shutil.copy2(file_path, checkpoint_dir / file_path.name)

        if self.context_file.exists():
            shutil.copy2(self.context_file, checkpoint_dir / "CONTEXT.json")

        logger.info(f"Created checkpoint {checkpoint_id} for agent {self.agent_id}")
        return checkpoint_id

    def restore_checkpoint(self, checkpoint_id: str):
        """
        Restore from a checkpoint.

        Args:
            checkpoint_id: Checkpoint to restore
        """
        checkpoint_dir = self.workspace_dir / "checkpoints" / checkpoint_id

        if not checkpoint_dir.exists():
            raise ValueError(f"Checkpoint {checkpoint_id} not found")

        # Restore files
        import shutil
        for file_path in checkpoint_dir.glob("*"):
            shutil.copy2(file_path, self.workspace_dir / file_path.name)

        logger.info(f"Restored checkpoint {checkpoint_id} for agent {self.agent_id}")

    def cleanup_old_checkpoints(self, keep_last: int = 5):
        """
        Clean up old checkpoints.

        Args:
            keep_last: Number of checkpoints to keep
        """
        checkpoints_dir = self.workspace_dir / "checkpoints"

        if not checkpoints_dir.exists():
            return

        # Get all checkpoints sorted by modification time
        checkpoints = sorted(
            checkpoints_dir.iterdir(),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        # Remove old ones
        for checkpoint in checkpoints[keep_last:]:
            import shutil
            shutil.rmtree(checkpoint)
            logger.debug(f"Removed old checkpoint {checkpoint.name}")

    def export_workspace(self) -> Dict[str, Any]:
        """
        Export entire workspace as dictionary.

        Returns:
            Workspace data
        """
        return {
            "agent_id": self.agent_id,
            "notes": self.read_notes(),
            "context": self.load_context(),
            "created_at": self.workspace_dir.stat().st_ctime,
            "size_bytes": sum(
                f.stat().st_size for f in self.workspace_dir.rglob("*") if f.is_file()
            )
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get workspace statistics.

        Returns:
            Statistics dictionary
        """
        total_size = sum(
            f.stat().st_size for f in self.workspace_dir.rglob("*") if f.is_file()
        )

        note_count = len(list(self.workspace_dir.glob("*.md")))
        checkpoint_count = len(list((self.workspace_dir / "checkpoints").glob("*"))) if (
            self.workspace_dir / "checkpoints"
        ).exists() else 0

        return {
            "agent_id": self.agent_id,
            "total_size_bytes": total_size,
            "note_count": note_count,
            "checkpoint_count": checkpoint_count,
            "workspace_path": str(self.workspace_dir)
        }


class WorkspaceManager:
    """
    Manages workspaces for multiple agents.

    Central point for workspace operations across agents.
    """

    def __init__(self, base_dir: str = ".brain/workspaces"):
        """
        Initialize workspace manager.

        Args:
            base_dir: Base directory for workspaces
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.workspaces: Dict[str, AgentWorkspace] = {}

    def get_workspace(self, agent_id: str) -> AgentWorkspace:
        """
        Get or create workspace for agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Agent workspace
        """
        if agent_id not in self.workspaces:
            self.workspaces[agent_id] = AgentWorkspace(agent_id, str(self.base_dir))

        return self.workspaces[agent_id]

    def list_agents(self) -> List[str]:
        """
        List all agents with workspaces.

        Returns:
            List of agent IDs
        """
        return [d.name for d in self.base_dir.iterdir() if d.is_dir()]

    def delete_workspace(self, agent_id: str):
        """
        Delete an agent's workspace.

        Args:
            agent_id: Agent to delete
        """
        workspace_dir = self.base_dir / agent_id

        if workspace_dir.exists():
            import shutil
            shutil.rmtree(workspace_dir)
            logger.info(f"Deleted workspace for agent {agent_id}")

        if agent_id in self.workspaces:
            del self.workspaces[agent_id]

    def get_total_size(self) -> int:
        """
        Get total size of all workspaces.

        Returns:
            Size in bytes
        """
        return sum(
            f.stat().st_size for f in self.base_dir.rglob("*") if f.is_file()
        )


# Global workspace manager
_workspace_manager: Optional[WorkspaceManager] = None


def get_workspace_manager() -> WorkspaceManager:
    """Get or create global workspace manager."""
    global _workspace_manager
    if _workspace_manager is None:
        _workspace_manager = WorkspaceManager()
    return _workspace_manager