"""Training data management and validation"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from brain.config import settings
from brain.training.models import TrainingDataset

logger = logging.getLogger(__name__)


class DataManager:
    """Manages training datasets"""

    def __init__(self):
        self.data_dir = settings.data_dir / "training_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def get_agent_data_dir(self, agent_id: str) -> Path:
        """Get training data directory for an agent"""
        agent_dir = self.data_dir / agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)
        return agent_dir

    def validate_jsonl_format(self, file_path: Path) -> Tuple[bool, List[str], Dict[str, Any]]:
        """
        Validate JSONL training data format

        Returns:
            (is_valid, errors, stats)
        """
        errors = []
        stats = {
            "num_examples": 0,
            "num_tokens": 0,
            "roles_found": set(),
            "avg_message_length": 0,
        }

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            if not lines:
                errors.append("File is empty")
                return False, errors, stats

            total_message_length = 0

            for line_num, line in enumerate(lines, 1):
                line = line.strip()
                if not line:
                    continue  # Skip empty lines

                # Parse JSON
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"Line {line_num}: Invalid JSON - {str(e)}")
                    continue

                # Validate structure
                if "messages" not in data:
                    errors.append(f"Line {line_num}: Missing 'messages' field")
                    continue

                messages = data["messages"]
                if not isinstance(messages, list):
                    errors.append(f"Line {line_num}: 'messages' must be a list")
                    continue

                if len(messages) == 0:
                    errors.append(f"Line {line_num}: 'messages' list is empty")
                    continue

                # Validate each message
                for msg_idx, msg in enumerate(messages):
                    if not isinstance(msg, dict):
                        errors.append(
                            f"Line {line_num}, message {msg_idx}: Message must be a dict"
                        )
                        continue

                    if "role" not in msg:
                        errors.append(
                            f"Line {line_num}, message {msg_idx}: Missing 'role' field"
                        )
                        continue

                    if "content" not in msg:
                        errors.append(
                            f"Line {line_num}, message {msg_idx}: Missing 'content' field"
                        )
                        continue

                    role = msg["role"]
                    content = msg["content"]

                    if role not in ["system", "user", "assistant"]:
                        errors.append(
                            f"Line {line_num}, message {msg_idx}: Invalid role '{role}' "
                            f"(must be 'system', 'user', or 'assistant')"
                        )

                    if not isinstance(content, str):
                        errors.append(
                            f"Line {line_num}, message {msg_idx}: 'content' must be a string"
                        )
                        continue

                    if not content.strip():
                        errors.append(
                            f"Line {line_num}, message {msg_idx}: 'content' is empty"
                        )

                    stats["roles_found"].add(role)
                    total_message_length += len(content)
                    # Rough token estimate (1 token ≈ 4 characters)
                    stats["num_tokens"] += len(content) // 4

                stats["num_examples"] += 1

            # Check for at least user and assistant roles
            if "user" not in stats["roles_found"]:
                errors.append("Dataset must contain at least one 'user' message")

            if "assistant" not in stats["roles_found"]:
                errors.append("Dataset must contain at least one 'assistant' message")

            # Calculate average
            if stats["num_examples"] > 0:
                stats["avg_message_length"] = total_message_length / stats["num_examples"]

            # Convert set to list for JSON serialization
            stats["roles_found"] = list(stats["roles_found"])

            is_valid = len(errors) == 0

            return is_valid, errors, stats

        except Exception as e:
            logger.error(f"Error validating file {file_path}: {e}")
            errors.append(f"Unexpected error: {str(e)}")
            return False, errors, stats

    async def upload_dataset(
        self,
        agent_id: str,
        file_path: Path,
        dataset_name: Optional[str] = None,
    ) -> TrainingDataset:
        """
        Upload and validate a training dataset

        Args:
            agent_id: Agent ID
            file_path: Path to uploaded JSONL file
            dataset_name: Optional name for the dataset

        Returns:
            TrainingDataset object

        Raises:
            ValueError: If validation fails
        """
        # Generate dataset name if not provided
        if not dataset_name:
            # Use file hash for uniqueness
            with open(file_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()[:8]
            dataset_name = f"dataset_{file_hash}"

        # Validate format
        is_valid, errors, stats = self.validate_jsonl_format(file_path)

        # Create dataset metadata
        agent_data_dir = self.get_agent_data_dir(agent_id)
        final_path = agent_data_dir / f"{dataset_name}.jsonl"

        # Copy file to final location
        if file_path != final_path:
            import shutil

            shutil.copy2(file_path, final_path)

        dataset = TrainingDataset(
            name=dataset_name,
            agent_id=agent_id,
            file_path=final_path,
            num_examples=stats.get("num_examples", 0),
            num_tokens=stats.get("num_tokens", 0),
            avg_tokens_per_example=(
                stats.get("avg_message_length", 0) // 4  # Rough token estimate
            ),
            is_valid=is_valid,
            validation_errors=errors,
        )

        # Save metadata
        metadata_path = agent_data_dir / f"{dataset_name}.json"
        with open(metadata_path, "w") as f:
            json.dump(dataset.to_dict(), f, indent=2)

        if not is_valid:
            error_msg = "Dataset validation failed:\n" + "\n".join(errors[:10])
            if len(errors) > 10:
                error_msg += f"\n... and {len(errors) - 10} more errors"
            raise ValueError(error_msg)

        logger.info(
            f"Uploaded dataset '{dataset_name}' for agent '{agent_id}': "
            f"{stats['num_examples']} examples, ~{stats['num_tokens']} tokens"
        )

        return dataset

    def list_datasets(self, agent_id: str) -> List[TrainingDataset]:
        """List all datasets for an agent"""
        agent_data_dir = self.get_agent_data_dir(agent_id)
        datasets = []

        for metadata_file in agent_data_dir.glob("*.json"):
            try:
                with open(metadata_file) as f:
                    data = json.load(f)
                datasets.append(
                    TrainingDataset(
                        name=data["name"],
                        agent_id=data["agent_id"],
                        file_path=Path(data["file_path"]),
                        created_at=data.get("created_at", 0),
                        num_examples=data.get("num_examples", 0),
                        num_tokens=data.get("num_tokens", 0),
                        avg_tokens_per_example=data.get("avg_tokens_per_example", 0),
                        is_valid=data.get("is_valid", False),
                        validation_errors=data.get("validation_errors", []),
                    )
                )
            except Exception as e:
                logger.error(f"Error loading dataset metadata from {metadata_file}: {e}")

        return datasets

    def get_dataset(self, agent_id: str, dataset_name: str) -> Optional[TrainingDataset]:
        """Get a specific dataset"""
        agent_data_dir = self.get_agent_data_dir(agent_id)
        metadata_file = agent_data_dir / f"{dataset_name}.json"

        if not metadata_file.exists():
            return None

        try:
            with open(metadata_file) as f:
                data = json.load(f)
            return TrainingDataset(
                name=data["name"],
                agent_id=data["agent_id"],
                file_path=Path(data["file_path"]),
                created_at=data.get("created_at", 0),
                num_examples=data.get("num_examples", 0),
                num_tokens=data.get("num_tokens", 0),
                avg_tokens_per_example=data.get("avg_tokens_per_example", 0),
                is_valid=data.get("is_valid", False),
                validation_errors=data.get("validation_errors", []),
            )
        except Exception as e:
            logger.error(f"Error loading dataset {dataset_name}: {e}")
            return None

    def delete_dataset(self, agent_id: str, dataset_name: str) -> bool:
        """Delete a dataset"""
        agent_data_dir = self.get_agent_data_dir(agent_id)

        jsonl_file = agent_data_dir / f"{dataset_name}.jsonl"
        metadata_file = agent_data_dir / f"{dataset_name}.json"

        deleted = False

        if jsonl_file.exists():
            jsonl_file.unlink()
            deleted = True

        if metadata_file.exists():
            metadata_file.unlink()
            deleted = True

        if deleted:
            logger.info(f"Deleted dataset '{dataset_name}' for agent '{agent_id}'")

        return deleted

    def create_example_dataset(self, agent_id: str) -> TrainingDataset:
        """Create an example training dataset for testing"""
        agent_data_dir = self.get_agent_data_dir(agent_id)
        example_file = agent_data_dir / "example_dataset.jsonl"

        example_data = [
            {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful AI assistant specializing in customer support.",
                    },
                    {"role": "user", "content": "How do I reset my password?"},
                    {
                        "role": "assistant",
                        "content": "To reset your password:\n1. Go to the login page\n2. Click 'Forgot Password'\n3. Enter your email address\n4. Check your email for a reset link\n5. Follow the link and create a new password",
                    },
                ]
            },
            {
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful AI assistant specializing in customer support.",
                    },
                    {"role": "user", "content": "What are your business hours?"},
                    {
                        "role": "assistant",
                        "content": "Our customer support is available:\n- Monday-Friday: 9 AM - 6 PM EST\n- Saturday: 10 AM - 4 PM EST\n- Sunday: Closed\n\nFor urgent issues outside these hours, please use our emergency hotline.",
                    },
                ]
            },
            {
                "messages": [
                    {"role": "user", "content": "How do I cancel my subscription?"},
                    {
                        "role": "assistant",
                        "content": "To cancel your subscription:\n1. Log into your account\n2. Go to Settings > Billing\n3. Click 'Cancel Subscription'\n4. Confirm the cancellation\n\nYour subscription will remain active until the end of your current billing period.",
                    },
                ]
            },
        ]

        with open(example_file, "w", encoding="utf-8") as f:
            for example in example_data:
                f.write(json.dumps(example) + "\n")

        # Validate and register
        is_valid, errors, stats = self.validate_jsonl_format(example_file)

        dataset = TrainingDataset(
            name="example_dataset",
            agent_id=agent_id,
            file_path=example_file,
            num_examples=stats.get("num_examples", 0),
            num_tokens=stats.get("num_tokens", 0),
            avg_tokens_per_example=stats.get("avg_message_length", 0) // 4,
            is_valid=is_valid,
            validation_errors=errors,
        )

        # Save metadata
        metadata_path = agent_data_dir / "example_dataset.json"
        with open(metadata_path, "w") as f:
            json.dump(dataset.to_dict(), f, indent=2)

        logger.info(f"Created example dataset for agent '{agent_id}'")

        return dataset


# Global instance
data_manager = DataManager()
