"""
Task classification for intelligent model routing.

Analyzes tasks to determine type, complexity, and requirements.
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """Types of tasks."""
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    CODE_EXPLANATION = "code_explanation"
    DEBUGGING = "debugging"
    GENERAL_CHAT = "general_chat"
    QUESTION_ANSWERING = "question_answering"
    SUMMARIZATION = "summarization"
    TRANSLATION = "translation"
    CREATIVE_WRITING = "creative_writing"
    ANALYSIS = "analysis"
    MATH = "math"
    VISION = "vision"
    REASONING = "reasoning"
    DATA_PROCESSING = "data_processing"
    UNKNOWN = "unknown"


class TaskComplexity(Enum):
    """Task complexity levels."""
    SIMPLE = "simple"  # Quick, straightforward tasks
    MODERATE = "moderate"  # Standard complexity
    COMPLEX = "complex"  # Multi-step or challenging tasks
    VERY_COMPLEX = "very_complex"  # Highly complex reasoning


@dataclass
class TaskRequirements:
    """Requirements for task execution."""
    task_type: TaskType
    complexity: TaskComplexity
    estimated_tokens: int
    requires_code: bool = False
    requires_vision: bool = False
    requires_reasoning: bool = False
    requires_math: bool = False
    requires_creativity: bool = False
    requires_factual: bool = False
    language: str = "en"
    context_length: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_type": self.task_type.value,
            "complexity": self.complexity.value,
            "estimated_tokens": self.estimated_tokens,
            "requires_code": self.requires_code,
            "requires_vision": self.requires_vision,
            "requires_reasoning": self.requires_reasoning,
            "requires_math": self.requires_math,
            "requires_creativity": self.requires_creativity,
            "requires_factual": self.requires_factual,
            "language": self.language,
            "context_length": self.context_length,
            "metadata": self.metadata
        }


class TaskClassifier:
    """
    Classifies tasks to determine optimal model routing.

    Features:
    - Task type detection
    - Complexity assessment
    - Requirement analysis
    - Language detection
    """

    def __init__(self):
        """Initialize task classifier."""
        # Task type patterns
        self.task_patterns = {
            TaskType.CODE_GENERATION: [
                r"write\s+(?:a\s+)?(?:function|class|code|script|program)",
                r"implement\s+\w+",
                r"create\s+(?:a\s+)?(?:function|class|api|service)",
                r"code\s+(?:for|to)\s+",
                r"generate\s+(?:code|script)",
            ],
            TaskType.CODE_REVIEW: [
                r"review\s+(?:this\s+)?code",
                r"check\s+(?:this\s+)?(?:code|function)",
                r"find\s+(?:bugs|issues|problems)\s+in",
                r"improve\s+(?:this\s+)?code",
                r"optimize\s+(?:this\s+)?(?:code|function)",
            ],
            TaskType.CODE_EXPLANATION: [
                r"explain\s+(?:this\s+)?(?:code|function|script)",
                r"what\s+does\s+this\s+(?:code|function)\s+do",
                r"how\s+does\s+(?:this\s+)?(?:code|function)\s+work",
                r"understand\s+(?:this\s+)?code",
            ],
            TaskType.DEBUGGING: [
                r"debug\s+",
                r"fix\s+(?:this\s+)?(?:error|bug|issue)",
                r"(?:error|exception|bug)(?:\s+message)?:?\s*",
                r"why\s+(?:is|does).*(?:not\s+work|fail|error)",
            ],
            TaskType.QUESTION_ANSWERING: [
                r"^what\s+(?:is|are)",
                r"^how\s+(?:do|does|can|to)",
                r"^why\s+(?:is|are|do|does)",
                r"^when\s+(?:is|are|do|does)",
                r"^where\s+(?:is|are|do|does)",
                r"^who\s+(?:is|are)",
                r"^(?:can|could)\s+you\s+(?:tell|explain)",
            ],
            TaskType.SUMMARIZATION: [
                r"summar(?:ize|y)",
                r"(?:give|provide)\s+(?:a\s+)?(?:summary|overview)",
                r"key\s+points",
                r"main\s+(?:points|ideas|takeaways)",
                r"tl;?dr",
            ],
            TaskType.TRANSLATION: [
                r"translate\s+(?:this|from|to)",
                r"(?:in|to)\s+(?:english|spanish|french|german|chinese|japanese)",
                r"what\s+(?:is|does).*(?:in|mean\s+in)\s+\w+",
            ],
            TaskType.CREATIVE_WRITING: [
                r"write\s+(?:a\s+)?(?:story|poem|essay|article|blog)",
                r"create\s+(?:a\s+)?(?:story|narrative|fiction)",
                r"generate\s+(?:creative|original)",
                r"compose\s+",
            ],
            TaskType.MATH: [
                r"calculate\s+",
                r"solve\s+(?:for|this)",
                r"what\s+is\s+\d+\s*[\+\-\*\/]",
                r"(?:derivative|integral|equation|formula)",
                r"math(?:ematical)?(?:\s+problem)?",
            ],
            TaskType.VISION: [
                r"(?:look|see|view)\s+(?:at\s+)?(?:this|the)\s+(?:image|picture|photo)",
                r"what\s+(?:is|are)\s+in\s+(?:this|the)\s+(?:image|picture)",
                r"describe\s+(?:this|the)\s+(?:image|picture|visual)",
                r"analyze\s+(?:this|the)\s+(?:image|picture)",
                r"image\s+(?:contains|shows)",
            ],
            TaskType.REASONING: [
                r"reason\s+(?:about|through)",
                r"think\s+(?:about|through)\s+(?:this|step)",
                r"logical(?:ly)?\s+",
                r"deduce\s+",
                r"infer\s+",
                r"step[\s\-]by[\s\-]step",
            ],
            TaskType.ANALYSIS: [
                r"analyze\s+",
                r"evaluate\s+",
                r"assess\s+",
                r"compare\s+(?:and\s+contrast)?",
                r"examine\s+",
                r"investigate\s+",
            ],
        }

        # Complexity indicators
        self.complexity_indicators = {
            "simple": [
                r"^(?:hi|hello|hey)",
                r"^(?:what|who|when|where)\s+is\s+",
                r"simple\s+",
                r"basic\s+",
                r"quick\s+",
            ],
            "complex": [
                r"complex\s+",
                r"advanced\s+",
                r"detailed\s+",
                r"comprehensive\s+",
                r"in[\s\-]depth\s+",
                r"multi[\s\-](?:step|part)",
                r"architect(?:ure)?",
                r"system\s+design",
            ],
            "very_complex": [
                r"very\s+complex",
                r"extremely\s+",
                r"highly\s+(?:complex|advanced)",
                r"enterprise[\s\-](?:level|grade)",
                r"production[\s\-]ready",
                r"scalable\s+",
            ],
        }

        # Language indicators
        self.language_patterns = {
            "code": [
                r"```\w*\n",  # Code blocks
                r"(?:def|class|function|var|let|const)\s+\w+",
                r"(?:if|else|for|while|return)\s*\(",
                r"(?:import|from|require)\s+",
            ],
            "math": [
                r"\d+\s*[\+\-\*\/\^]\s*\d+",
                r"\\[a-zA-Z]+(?:\{[^}]*\})?",  # LaTeX
                r"(?:sin|cos|tan|log|exp|sqrt)\s*\(",
            ],
        }

    def classify(
        self,
        text: str,
        context: Optional[List[Dict[str, str]]] = None
    ) -> TaskRequirements:
        """
        Classify a task based on text and context.

        Args:
            text: Task description or query
            context: Conversation context

        Returns:
            Task requirements
        """
        # Detect task type
        task_type = self._detect_task_type(text)

        # Assess complexity
        complexity = self._assess_complexity(text, task_type)

        # Detect requirements
        requires_code = self._requires_code(text)
        requires_vision = self._requires_vision(text)
        requires_reasoning = self._requires_reasoning(text, task_type)
        requires_math = self._requires_math(text)
        requires_creativity = self._requires_creativity(task_type)
        requires_factual = self._requires_factual(task_type)

        # Estimate tokens
        estimated_tokens = self._estimate_tokens(text, complexity, context)

        # Calculate context length
        context_length = self._calculate_context_length(text, context)

        # Detect language
        language = self._detect_language(text)

        requirements = TaskRequirements(
            task_type=task_type,
            complexity=complexity,
            estimated_tokens=estimated_tokens,
            requires_code=requires_code,
            requires_vision=requires_vision,
            requires_reasoning=requires_reasoning,
            requires_math=requires_math,
            requires_creativity=requires_creativity,
            requires_factual=requires_factual,
            language=language,
            context_length=context_length
        )

        logger.debug(f"Classified task: {requirements.to_dict()}")

        return requirements

    def _detect_task_type(self, text: str) -> TaskType:
        """Detect the type of task."""
        text_lower = text.lower()

        # Check each task type pattern
        for task_type, patterns in self.task_patterns.items():
            for pattern in patterns:
                if re.search(pattern, text_lower):
                    return task_type

        # Check for code presence
        if "```" in text or self._requires_code(text):
            if any(word in text_lower for word in ["review", "check", "improve"]):
                return TaskType.CODE_REVIEW
            elif any(word in text_lower for word in ["explain", "understand", "what does"]):
                return TaskType.CODE_EXPLANATION
            else:
                return TaskType.CODE_GENERATION

        # Default to general chat
        return TaskType.GENERAL_CHAT

    def _assess_complexity(self, text: str, task_type: TaskType) -> TaskComplexity:
        """Assess task complexity."""
        text_lower = text.lower()

        # Check explicit complexity indicators
        for indicator in self.complexity_indicators["very_complex"]:
            if re.search(indicator, text_lower):
                return TaskComplexity.VERY_COMPLEX

        for indicator in self.complexity_indicators["complex"]:
            if re.search(indicator, text_lower):
                return TaskComplexity.COMPLEX

        for indicator in self.complexity_indicators["simple"]:
            if re.search(indicator, text_lower):
                return TaskComplexity.SIMPLE

        # Task type based complexity
        if task_type in [TaskType.REASONING, TaskType.ANALYSIS]:
            return TaskComplexity.COMPLEX
        elif task_type in [TaskType.CODE_GENERATION, TaskType.DEBUGGING]:
            # Check code complexity
            if len(text) > 500 or text.count("\n") > 20:
                return TaskComplexity.COMPLEX
            return TaskComplexity.MODERATE
        elif task_type == TaskType.GENERAL_CHAT:
            return TaskComplexity.SIMPLE

        # Text length based
        if len(text) > 1000:
            return TaskComplexity.COMPLEX
        elif len(text) > 200:
            return TaskComplexity.MODERATE

        return TaskComplexity.MODERATE

    def _requires_code(self, text: str) -> bool:
        """Check if task requires code capabilities."""
        for pattern in self.language_patterns["code"]:
            if re.search(pattern, text):
                return True

        code_keywords = ["function", "class", "variable", "loop", "algorithm",
                        "api", "database", "frontend", "backend", "debug"]
        return any(keyword in text.lower() for keyword in code_keywords)

    def _requires_vision(self, text: str) -> bool:
        """Check if task requires vision capabilities."""
        vision_keywords = ["image", "picture", "photo", "visual", "screenshot",
                          "diagram", "chart", "graph", "see", "look at"]
        return any(keyword in text.lower() for keyword in vision_keywords)

    def _requires_reasoning(self, text: str, task_type: TaskType) -> bool:
        """Check if task requires complex reasoning."""
        if task_type in [TaskType.REASONING, TaskType.ANALYSIS]:
            return True

        reasoning_keywords = ["reason", "think", "deduce", "infer", "conclude",
                             "step-by-step", "logical", "analyze", "evaluate"]
        return any(keyword in text.lower() for keyword in reasoning_keywords)

    def _requires_math(self, text: str) -> bool:
        """Check if task requires math capabilities."""
        # Check for math patterns
        for pattern in self.language_patterns["math"]:
            if re.search(pattern, text):
                return True

        math_keywords = ["calculate", "solve", "equation", "formula", "derivative",
                        "integral", "matrix", "vector", "probability", "statistics"]
        return any(keyword in text.lower() for keyword in math_keywords)

    def _requires_creativity(self, task_type: TaskType) -> bool:
        """Check if task requires creativity."""
        return task_type in [
            TaskType.CREATIVE_WRITING,
            TaskType.GENERAL_CHAT  # Some chat requires creativity
        ]

    def _requires_factual(self, task_type: TaskType) -> bool:
        """Check if task requires factual accuracy."""
        return task_type in [
            TaskType.QUESTION_ANSWERING,
            TaskType.ANALYSIS,
            TaskType.SUMMARIZATION
        ]

    def _estimate_tokens(
        self,
        text: str,
        complexity: TaskComplexity,
        context: Optional[List[Dict[str, str]]]
    ) -> int:
        """Estimate required tokens for response."""
        base_estimate = len(text.split()) * 2  # Rough estimate

        # Complexity multiplier
        complexity_multipliers = {
            TaskComplexity.SIMPLE: 1.5,
            TaskComplexity.MODERATE: 3,
            TaskComplexity.COMPLEX: 5,
            TaskComplexity.VERY_COMPLEX: 10
        }

        estimate = base_estimate * complexity_multipliers[complexity]

        # Add context overhead
        if context:
            context_tokens = sum(len(msg.get("content", "").split()) for msg in context)
            estimate += context_tokens

        return min(int(estimate), 4096)  # Cap at reasonable limit

    def _calculate_context_length(
        self,
        text: str,
        context: Optional[List[Dict[str, str]]]
    ) -> int:
        """Calculate total context length."""
        text_length = len(text)

        if context:
            context_length = sum(len(msg.get("content", "")) for msg in context)
            return text_length + context_length

        return text_length

    def _detect_language(self, text: str) -> str:
        """Detect the language of the text."""
        # Simple language detection (in production, use proper NLP)
        language_indicators = {
            "es": ["hola", "cómo", "qué", "por favor", "gracias"],
            "fr": ["bonjour", "comment", "merci", "s'il vous plaît"],
            "de": ["hallo", "wie", "danke", "bitte"],
            "zh": ["你好", "什么", "谢谢"],
            "ja": ["こんにちは", "ありがとう"],
        }

        text_lower = text.lower()
        for lang, indicators in language_indicators.items():
            if any(word in text_lower for word in indicators):
                return lang

        return "en"  # Default to English