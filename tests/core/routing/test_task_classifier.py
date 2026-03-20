"""
Tests for task classification system.
"""

import pytest

from brain.core.routing.task_classifier import (
    TaskClassifier,
    TaskType,
    TaskComplexity,
    TaskRequirements
)


class TestTaskClassifier:
    """Test task classification functionality."""

    @pytest.fixture
    def classifier(self):
        """Create a task classifier."""
        return TaskClassifier()

    def test_detect_code_generation(self, classifier):
        """Test detection of code generation tasks."""
        texts = [
            "Write a function to sort an array",
            "Implement a binary search algorithm",
            "Create a class for managing user data",
            "Generate code to connect to a database"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.CODE_GENERATION
            assert requirements.requires_code is True

    def test_detect_code_review(self, classifier):
        """Test detection of code review tasks."""
        texts = [
            "Review this code for bugs",
            "Check this function for issues",
            "Improve this code for better performance",
            "Optimize this algorithm"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.CODE_REVIEW
            assert requirements.requires_code is True

    def test_detect_code_explanation(self, classifier):
        """Test detection of code explanation tasks."""
        texts = [
            "Explain this code snippet",
            "What does this function do?",
            "How does this algorithm work?",
            "Help me understand this code"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.CODE_EXPLANATION

    def test_detect_debugging(self, classifier):
        """Test detection of debugging tasks."""
        texts = [
            "Debug this error: IndexError",
            "Fix this bug in my code",
            "Why is this function not working?",
            "Error message: undefined variable"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.DEBUGGING

    def test_detect_vision_tasks(self, classifier):
        """Test detection of vision tasks."""
        texts = [
            "Look at this image and describe it",
            "What is in this picture?",
            "Analyze this screenshot",
            "Describe what you see in the photo"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.VISION
            assert requirements.requires_vision is True

    def test_detect_math_tasks(self, classifier):
        """Test detection of math tasks."""
        texts = [
            "Calculate the derivative of x^2",
            "Solve this equation: 2x + 5 = 15",
            "What is 125 * 37?",
            "Find the integral of sin(x)"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.MATH or requirements.requires_math

    def test_detect_reasoning_tasks(self, classifier):
        """Test detection of reasoning tasks."""
        texts = [
            "Think through this step by step",
            "Reason about the implications",
            "Logically deduce the answer",
            "Analyze this problem step-by-step"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.REASONING or requirements.requires_reasoning

    def test_complexity_assessment_simple(self, classifier):
        """Test simple complexity assessment."""
        texts = [
            "Hi",
            "Hello there",
            "What is your name?",
            "Simple question"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.complexity == TaskComplexity.SIMPLE

    def test_complexity_assessment_complex(self, classifier):
        """Test complex task assessment."""
        texts = [
            "Design a complex distributed system architecture",
            "Implement an advanced machine learning pipeline",
            "Create a comprehensive testing framework",
            "Build a multi-step data processing system"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.complexity in [TaskComplexity.COMPLEX, TaskComplexity.VERY_COMPLEX]

    def test_code_detection(self, classifier):
        """Test code presence detection."""
        text_with_code = """
        Here's my function:
        ```python
        def hello(name):
            return f"Hello {name}"
        ```
        Can you explain it?
        """

        requirements = classifier.classify(text_with_code)
        assert requirements.requires_code is True
        assert requirements.task_type == TaskType.CODE_EXPLANATION

    def test_language_detection(self, classifier):
        """Test language detection."""
        # Spanish
        requirements = classifier.classify("Hola, ¿cómo estás?")
        assert requirements.language == "es"

        # French
        requirements = classifier.classify("Bonjour, comment allez-vous?")
        assert requirements.language == "fr"

        # English (default)
        requirements = classifier.classify("Hello, how are you?")
        assert requirements.language == "en"

    def test_token_estimation(self, classifier):
        """Test token estimation."""
        # Short text
        short_text = "Hello"
        requirements = classifier.classify(short_text)
        assert requirements.estimated_tokens < 100

        # Long complex text
        long_text = "x" * 1000 + " complex task"
        requirements = classifier.classify(long_text)
        assert requirements.estimated_tokens > 1000

    def test_context_length_calculation(self, classifier):
        """Test context length calculation."""
        text = "What is AI?"
        context = [
            {"role": "user", "content": "Tell me about technology"},
            {"role": "assistant", "content": "Technology is..."}
        ]

        requirements = classifier.classify(text, context)
        assert requirements.context_length > len(text)

    def test_creative_writing_detection(self, classifier):
        """Test creative writing detection."""
        texts = [
            "Write a short story about a robot",
            "Create a poem about nature",
            "Compose an essay on climate change"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.CREATIVE_WRITING
            assert requirements.requires_creativity is True

    def test_summarization_detection(self, classifier):
        """Test summarization detection."""
        texts = [
            "Summarize this article",
            "Give me the key points",
            "TL;DR of this document",
            "Provide a summary"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.SUMMARIZATION

    def test_translation_detection(self, classifier):
        """Test translation detection."""
        texts = [
            "Translate this to Spanish",
            "What does 'bonjour' mean in English?",
            "Convert this text to German"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.TRANSLATION

    def test_question_answering_detection(self, classifier):
        """Test Q&A detection."""
        texts = [
            "What is quantum computing?",
            "How does photosynthesis work?",
            "Why is the sky blue?",
            "When was Python created?"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.QUESTION_ANSWERING
            assert requirements.requires_factual is True

    def test_analysis_detection(self, classifier):
        """Test analysis task detection."""
        texts = [
            "Analyze this data",
            "Evaluate the performance",
            "Compare these two approaches",
            "Examine the results"
        ]

        for text in texts:
            requirements = classifier.classify(text)
            assert requirements.task_type == TaskType.ANALYSIS