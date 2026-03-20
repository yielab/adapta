"""
Data formatters for different training paradigms
"""

from typing import Dict, List, Any, Optional
import json
import logging
from .base import DataFormatter, ProcessedData

logger = logging.getLogger(__name__)


class JSONLFormatter(DataFormatter):
    """
    Standard JSONL formatter for fine-tuning.
    Produces {"messages": [...]} format compatible with most LLM training.
    """

    def format(self, data: ProcessedData) -> Dict[str, Any]:
        """Format data into standard JSONL training format"""
        messages = []

        # Add system message if provided
        if 'system_prompt' in data.metadata:
            messages.append({
                "role": "system",
                "content": data.metadata['system_prompt']
            })

        # Parse content based on format type
        if data.format == 'conversation':
            # Already in conversation format
            messages.extend(self._parse_conversation(data.content))
        elif data.format == 'instruction':
            # Convert instruction format to conversation
            messages.extend(self._parse_instruction(data.content))
        else:
            # Raw content - create Q&A from it
            messages.extend(self._create_qa_from_raw(data.content))

        # Add metadata if configured
        formatted = {"messages": messages}
        if self.include_metadata:
            formatted["metadata"] = {
                "source": data.source.location,
                "type": data.source.type,
                "version": data.version_info.get('target_version') if data.version_info else None
            }

        # Add training weight if present
        if hasattr(data, 'training_weight'):
            formatted["weight"] = data.training_weight

        return formatted

    def _parse_conversation(self, content: str) -> List[Dict[str, str]]:
        """Parse conversation format content"""
        messages = []
        lines = content.split('\n')

        current_role = None
        current_content = []

        for line in lines:
            if line.startswith('User:'):
                if current_role:
                    messages.append({
                        "role": current_role,
                        "content": '\n'.join(current_content).strip()
                    })
                current_role = 'user'
                current_content = [line[5:].strip()]
            elif line.startswith('Assistant:'):
                if current_role:
                    messages.append({
                        "role": current_role,
                        "content": '\n'.join(current_content).strip()
                    })
                current_role = 'assistant'
                current_content = [line[10:].strip()]
            elif line.startswith('System:'):
                if current_role:
                    messages.append({
                        "role": current_role,
                        "content": '\n'.join(current_content).strip()
                    })
                current_role = 'system'
                current_content = [line[7:].strip()]
            elif current_role:
                current_content.append(line)

        # Add last message
        if current_role:
            messages.append({
                "role": current_role,
                "content": '\n'.join(current_content).strip()
            })

        return messages

    def _parse_instruction(self, content: str) -> List[Dict[str, str]]:
        """Parse instruction format content"""
        # Look for instruction-response pairs
        if '### Instruction:' in content and '### Response:' in content:
            parts = content.split('### Response:')
            instruction = parts[0].replace('### Instruction:', '').strip()
            response = parts[1].strip() if len(parts) > 1 else ''

            return [
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": response}
            ]

        # Fallback to treating as Q&A
        return self._create_qa_from_raw(content)

    def _create_qa_from_raw(self, content: str) -> List[Dict[str, str]]:
        """Create Q&A pairs from raw content"""
        # Split into chunks if too long
        chunks = self.chunk_content(content, chunk_size=1024)

        messages = []
        for i, chunk in enumerate(chunks):
            if i == 0:
                messages.append({
                    "role": "user",
                    "content": "Please explain the following documentation:"
                })
            messages.append({
                "role": "assistant",
                "content": chunk
            })

        return messages


class InstructionFormatter(DataFormatter):
    """
    Formatter for instruction-tuning datasets.
    Creates instruction-context-response triplets.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.instruction_templates = self.config.get('instruction_templates', {
            'explain': "Explain the following concept: {topic}",
            'implement': "Write code to implement: {task}",
            'fix': "Fix the following issue: {problem}",
            'convert': "Convert this {from_format} to {to_format}: {content}"
        })

    def format(self, data: ProcessedData) -> Dict[str, Any]:
        """Format data as instruction-response pairs"""
        instruction = self._generate_instruction(data)
        context = self._extract_context(data)
        response = self._generate_response(data)

        formatted = {
            "instruction": instruction,
            "response": response
        }

        if context:
            formatted["context"] = context

        # Add metadata
        if self.include_metadata:
            formatted["metadata"] = {
                "source": data.source.location,
                "domain": data.metadata.get('domain'),
                "difficulty": self._assess_difficulty(data)
            }

        return formatted

    def _generate_instruction(self, data: ProcessedData) -> str:
        """Generate instruction based on content type"""
        if data.source.type == 'api_documentation':
            api_elements = data.metadata.get('api_elements', {})
            if api_elements.get('functions'):
                return f"Explain how to use the {api_elements['functions'][0]} function"
            elif api_elements.get('classes'):
                return f"Describe the {api_elements['classes'][0]} class and its methods"

        elif data.source.type == 'change_record':
            version_info = data.metadata.get('version_info', {})
            if version_info.get('deprecated_items'):
                return "What has been deprecated in the latest version?"
            elif version_info.get('new_features'):
                return "What are the new features in this version?"

        # Default instruction
        return "Explain the following technical documentation:"

    def _extract_context(self, data: ProcessedData) -> Optional[str]:
        """Extract relevant context from data"""
        if 'code_examples' in data.metadata.get('api_elements', {}):
            examples = data.metadata['api_elements']['code_examples']
            if examples:
                return f"Example code:\n```{examples[0]['language']}\n{examples[0]['code']}\n```"
        return None

    def _generate_response(self, data: ProcessedData) -> str:
        """Generate appropriate response"""
        # Clean and format the content as response
        content = data.content

        # Add version-specific information if available
        if data.version_info:
            version = data.version_info.get('target_version')
            if version:
                content = f"For version {version}:\n\n{content}"

        return content

    def _assess_difficulty(self, data: ProcessedData) -> str:
        """Assess content difficulty level"""
        content_length = len(data.content)
        has_code = 'code_examples' in data.metadata.get('api_elements', {})

        if content_length > 2000 or has_code:
            return "advanced"
        elif content_length > 500:
            return "intermediate"
        else:
            return "beginner"


class ConversationFormatter(DataFormatter):
    """
    Formatter for multi-turn conversation datasets.
    Creates realistic dialogue flows for chat-based training.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.personas = self.config.get('personas', {
            'helpful': "You are a helpful assistant specializing in {domain}",
            'expert': "You are an expert in {domain} with deep knowledge of {topic}",
            'tutor': "You are a patient tutor teaching {domain} to beginners"
        })
        self.max_turns = self.config.get('max_turns', 5)

    def format(self, data: ProcessedData) -> Dict[str, Any]:
        """Format data as multi-turn conversation"""
        conversation = self._generate_conversation(data)

        formatted = {
            "messages": conversation,
            "turns": len([m for m in conversation if m['role'] == 'user'])
        }

        if self.include_metadata:
            formatted["metadata"] = {
                "source": data.source.location,
                "domain": data.metadata.get('domain', 'general'),
                "conversation_type": self._determine_conversation_type(data)
            }

        return formatted

    def _generate_conversation(self, data: ProcessedData) -> List[Dict[str, str]]:
        """Generate a multi-turn conversation from content"""
        messages = []

        # Add system prompt
        domain = data.metadata.get('domain', 'technical documentation')
        topic = self._extract_topic(data)
        persona = self.personas.get(data.metadata.get('persona', 'helpful'), self.personas['helpful'])
        system_prompt = persona.format(domain=domain, topic=topic)
        messages.append({"role": "system", "content": system_prompt})

        # Split content into Q&A turns
        chunks = self.chunk_content(data.content, chunk_size=512)

        for i, chunk in enumerate(chunks[:self.max_turns]):
            # Generate user question
            question = self._generate_question(chunk, i)
            messages.append({"role": "user", "content": question})

            # Add assistant response
            response = self._generate_answer(chunk, data)
            messages.append({"role": "assistant", "content": response})

        return messages

    def _extract_topic(self, data: ProcessedData) -> str:
        """Extract main topic from content"""
        # Look for headers or key terms
        lines = data.content.split('\n')
        for line in lines:
            if line.startswith('#'):
                return line.strip('#').strip()

        # Use first sentence as fallback
        return lines[0][:100] if lines else "technical concepts"

    def _generate_question(self, chunk: str, turn_num: int) -> str:
        """Generate contextual questions"""
        questions = [
            "Can you explain this concept?",
            "How does this work in practice?",
            "What are the key points here?",
            "Can you provide more details?",
            "What should I know about this?"
        ]

        # Extract key terms for more specific questions
        if 'function' in chunk.lower():
            return f"How do I use this function?"
        elif 'class' in chunk.lower():
            return f"What does this class do?"
        elif 'error' in chunk.lower():
            return f"How do I fix this error?"

        return questions[turn_num % len(questions)]

    def _generate_answer(self, chunk: str, data: ProcessedData) -> str:
        """Generate informative answer"""
        answer = chunk

        # Add code examples if available
        if 'api_elements' in data.metadata:
            examples = data.metadata['api_elements'].get('code_examples', [])
            if examples and len(answer) < 300:
                answer += f"\n\nHere's an example:\n```\n{examples[0]['code']}\n```"

        return answer

    def _determine_conversation_type(self, data: ProcessedData) -> str:
        """Determine the type of conversation"""
        if data.source.type == 'api_documentation':
            return 'technical_explanation'
        elif data.source.type == 'change_record':
            return 'migration_guide'
        elif 'code_examples' in data.metadata.get('api_elements', {}):
            return 'code_tutorial'
        else:
            return 'knowledge_transfer'


class DeltaTrainingFormatter(DataFormatter):
    """
    Specialized formatter for delta training strategy.
    Emphasizes version differences and migration paths.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.emphasis_old_way = self.config.get('emphasis_old_way', True)
        self.include_migration = self.config.get('include_migration', True)

    def format(self, data: ProcessedData) -> Dict[str, Any]:
        """Format data with version-specific emphasis"""
        if not data.version_info:
            # No version info, use standard formatting
            return JSONLFormatter(self.config).format(data)

        messages = self._create_versioned_messages(data)

        formatted = {
            "messages": messages,
            "version_context": {
                "from": data.version_info.get('base_version'),
                "to": data.version_info.get('target_version'),
                "is_breaking_change": self._is_breaking_change(data)
            }
        }

        # Apply training weight based on importance
        formatted["weight"] = self._calculate_weight(data)

        return formatted

    def _create_versioned_messages(self, data: ProcessedData) -> List[Dict[str, str]]:
        """Create messages that emphasize version differences"""
        messages = []

        # System prompt with version context
        target_version = data.version_info.get('target_version', 'latest')
        messages.append({
            "role": "system",
            "content": f"You are an expert in version {target_version}. Always provide answers specific to this version."
        })

        # If deprecated content, create negative example
        if self._is_deprecated(data):
            messages.extend([
                {"role": "user", "content": "How should I implement this feature?"},
                {"role": "assistant", "content": f"⚠️ The old approach is deprecated. Here's the correct way for version {target_version}:\n\n{data.content}"}
            ])
        else:
            # Regular version-specific content
            messages.extend([
                {"role": "user", "content": f"What's new in version {target_version}?"},
                {"role": "assistant", "content": data.content}
            ])

        # Add migration guidance if available
        if self.include_migration and 'migration_notes' in data.metadata.get('version_info', {}):
            notes = data.metadata['version_info']['migration_notes']
            if notes:
                messages.extend([
                    {"role": "user", "content": "How do I migrate from the old version?"},
                    {"role": "assistant", "content": '\n'.join(notes)}
                ])

        return messages

    def _is_deprecated(self, data: ProcessedData) -> bool:
        """Check if content contains deprecated information"""
        version_info = data.metadata.get('version_info', {})
        return len(version_info.get('deprecated_items', [])) > 0

    def _is_breaking_change(self, data: ProcessedData) -> bool:
        """Determine if this represents a breaking change"""
        content_lower = data.content.lower()
        breaking_indicators = ['breaking change', 'not compatible', 'removed', 'no longer supported']
        return any(indicator in content_lower for indicator in breaking_indicators)

    def _calculate_weight(self, data: ProcessedData) -> float:
        """Calculate training weight based on importance"""
        weight = 1.0

        # Increase weight for breaking changes
        if self._is_breaking_change(data):
            weight *= 2.0

        # Increase weight for migration content
        if 'migration_notes' in data.metadata.get('version_info', {}):
            weight *= 1.5

        # Decrease weight for deprecated content (but don't ignore)
        if self._is_deprecated(data):
            weight *= 0.7

        # Apply configured weight if present
        if hasattr(data, 'training_weight'):
            weight *= data.training_weight

        return weight