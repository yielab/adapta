"""
Domain-specific processors for enhanced training data quality.
Each processor understands the unique patterns and structures of its domain.
"""

import re
import json
import logging
from typing import Dict, Any, Optional, List
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class DomainProcessor(ABC):
    """Base class for domain-specific processors"""

    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}

    @abstractmethod
    async def process(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Process content according to domain-specific rules"""
        pass

    @abstractmethod
    def extract_concepts(self, text: str) -> List[str]:
        """Extract domain-specific concepts from text"""
        pass

    @abstractmethod
    def create_training_examples(self, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create domain-specific training examples"""
        pass


class DrupalProcessor(DomainProcessor):
    """
    Processor specialized for Drupal documentation and code.
    Understands hooks, modules, themes, entities, and Drupal patterns.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.hook_pattern = re.compile(r'hook_[a-z_]+')
        self.function_pattern = re.compile(r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
        self.service_pattern = re.compile(r'@[a-zA-Z_][a-zA-Z0-9._]*')
        self.entity_pattern = re.compile(r'(node|user|taxonomy_term|block|menu|view)s?')

    async def process(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process Drupal content to enhance training quality.

        - Extracts hooks, services, entities
        - Identifies code examples
        - Structures module documentation
        - Tags with Drupal version
        """
        processed = content.copy()
        text = content.get('content', '')

        # Extract Drupal-specific elements
        hooks = self.hook_pattern.findall(text)
        functions = self.function_pattern.findall(text)
        services = self.service_pattern.findall(text)
        entities = self.entity_pattern.findall(text.lower())

        # Extract code blocks
        code_blocks = re.findall(r'```(?:php|yaml|twig)?\n(.*?)```', text, re.DOTALL)

        # Enhance metadata
        metadata = processed.get('metadata', {})
        metadata.update({
            'hooks': list(set(hooks)),
            'functions': list(set(functions)),
            'services': list(set(services)),
            'entities': list(set(entities)),
            'has_code': len(code_blocks) > 0,
            'code_count': len(code_blocks),
            'drupal_version': self.config.get('version', '11')
        })
        processed['metadata'] = metadata

        # Structure content for better training
        if hooks:
            processed['concepts'] = self.extract_concepts(text)

        # Add structured summaries for hooks
        if hooks and code_blocks:
            processed['structured_content'] = self._structure_hook_documentation(
                hooks, code_blocks, text
            )

        logger.debug(f"Drupal processor found: {len(hooks)} hooks, {len(functions)} functions, {len(services)} services")

        return processed

    def extract_concepts(self, text: str) -> List[str]:
        """Extract Drupal-specific concepts"""
        concepts = []

        # Common Drupal concepts to look for
        drupal_concepts = {
            'hook': 'Drupal hooks',
            'module': 'Module development',
            'theme': 'Theming',
            'entity': 'Entity API',
            'form': 'Form API',
            'render': 'Render API',
            'cache': 'Cache API',
            'routing': 'Routing system',
            'service': 'Services',
            'plugin': 'Plugin system',
            'migration': 'Migration API',
            'configuration': 'Configuration management',
            'permission': 'Permissions',
            'block': 'Block system',
            'view': 'Views',
            'field': 'Field API'
        }

        text_lower = text.lower()
        for keyword, concept in drupal_concepts.items():
            if keyword in text_lower:
                concepts.append(concept)

        return list(set(concepts))

    def create_training_examples(self, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create Drupal-specific training examples.

        Generates Q&A pairs for:
        - Hook implementations
        - Module creation
        - Service usage
        - Entity operations
        - Theming questions
        """
        examples = []
        metadata = content.get('metadata', {})
        text = content.get('content', '')
        title = content.get('title', 'Drupal Documentation')

        # Hook implementation examples
        hooks = metadata.get('hooks', [])
        for hook in hooks[:3]:  # Limit to avoid too many similar examples
            examples.append({
                "messages": [
                    {"role": "user", "content": f"How do I implement {hook} in Drupal?"},
                    {"role": "assistant", "content": self._extract_hook_explanation(hook, text)}
                ]
            })

        # Service usage examples
        services = metadata.get('services', [])
        if services:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"How do I use the {services[0]} service in Drupal?"},
                    {"role": "assistant", "content": self._extract_service_explanation(services[0], text)}
                ]
            })

        # General module development
        if 'module' in text.lower():
            examples.append({
                "messages": [
                    {"role": "user", "content": f"Explain {title}"},
                    {"role": "assistant", "content": text[:2000]}  # Limit length
                ]
            })

        # Code examples
        code_blocks = re.findall(r'```(?:php)?\n(.*?)```', text, re.DOTALL)
        if code_blocks:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"Show me example code for {title}"},
                    {"role": "assistant", "content": f"Here's an example:\n\n```php\n{code_blocks[0]}\n```"}
                ]
            })

        return examples

    def _structure_hook_documentation(self, hooks: List[str], code_blocks: List[str], text: str) -> Dict[str, Any]:
        """Structure hook documentation for training"""
        structured = {
            "hooks": {},
            "examples": []
        }

        for hook in hooks[:5]:  # Process first 5 hooks
            # Find context around hook mention
            hook_context = self._extract_context(hook, text, 200)
            structured["hooks"][hook] = {
                "description": hook_context,
                "parameters": self._extract_parameters(hook, text),
                "return_value": self._extract_return_value(hook, text)
            }

        # Add code examples
        for code in code_blocks[:3]:
            if any(hook in code for hook in hooks):
                structured["examples"].append(code)

        return structured

    def _extract_hook_explanation(self, hook: str, text: str) -> str:
        """Extract explanation for a specific hook"""
        # Find text around hook mention
        context = self._extract_context(hook, text, 300)
        if context:
            return f"{hook} is used to {context}"
        return f"{hook} is a Drupal hook. Refer to the documentation for detailed usage."

    def _extract_service_explanation(self, service: str, text: str) -> str:
        """Extract explanation for a service"""
        context = self._extract_context(service, text, 300)
        if context:
            return f"The {service} service {context}"
        return f"The {service} service is available in Drupal's service container."

    def _extract_context(self, term: str, text: str, context_size: int = 200) -> str:
        """Extract context around a term"""
        index = text.lower().find(term.lower())
        if index != -1:
            start = max(0, index - context_size // 2)
            end = min(len(text), index + len(term) + context_size // 2)
            context = text[start:end]
            # Clean up the context
            context = re.sub(r'\s+', ' ', context).strip()
            return context
        return ""

    def _extract_parameters(self, hook: str, text: str) -> List[str]:
        """Try to extract parameters for a hook"""
        # Look for parameter patterns near hook definition
        pattern = rf'{hook}\s*\((.*?)\)'
        match = re.search(pattern, text)
        if match:
            params = match.group(1).split(',')
            return [p.strip() for p in params if p.strip()]
        return []

    def _extract_return_value(self, hook: str, text: str) -> str:
        """Try to extract return value info for a hook"""
        # Look for return value mentions
        context = self._extract_context(f"{hook} return", text, 100)
        if context:
            return context
        return "See documentation for return value details"


class ReactProcessor(DomainProcessor):
    """
    Processor specialized for React documentation and code.
    Understands components, hooks, JSX, state management, and React patterns.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.component_pattern = re.compile(r'(?:function|const|class)\s+([A-Z][a-zA-Z0-9]*)')
        self.hook_pattern = re.compile(r'use[A-Z][a-zA-Z0-9]*')
        self.jsx_pattern = re.compile(r'<([A-Z][a-zA-Z0-9]*)[^>]*>')

    async def process(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Process React content"""
        processed = content.copy()
        text = content.get('content', '')

        # Extract React-specific elements
        components = self.component_pattern.findall(text)
        hooks = self.hook_pattern.findall(text)
        jsx_elements = self.jsx_pattern.findall(text)

        # Extract code blocks
        code_blocks = re.findall(r'```(?:jsx?|typescript|tsx)?\n(.*?)```', text, re.DOTALL)

        # Enhance metadata
        metadata = processed.get('metadata', {})
        metadata.update({
            'components': list(set(components)),
            'hooks': list(set(hooks)),
            'jsx_elements': list(set(jsx_elements)),
            'has_code': len(code_blocks) > 0,
            'code_count': len(code_blocks),
            'react_version': self.config.get('version', '18')
        })
        processed['metadata'] = metadata

        logger.debug(f"React processor found: {len(components)} components, {len(hooks)} hooks")

        return processed

    def extract_concepts(self, text: str) -> List[str]:
        """Extract React-specific concepts"""
        concepts = []

        react_concepts = {
            'component': 'React Components',
            'hook': 'React Hooks',
            'state': 'State Management',
            'props': 'Component Props',
            'context': 'Context API',
            'redux': 'Redux',
            'router': 'React Router',
            'effect': 'Side Effects',
            'memo': 'Performance Optimization',
            'ref': 'Refs and DOM',
            'portal': 'React Portals',
            'suspense': 'React Suspense',
            'lazy': 'Code Splitting'
        }

        text_lower = text.lower()
        for keyword, concept in react_concepts.items():
            if keyword in text_lower:
                concepts.append(concept)

        return list(set(concepts))

    def create_training_examples(self, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create React-specific training examples"""
        examples = []
        metadata = content.get('metadata', {})
        text = content.get('content', '')
        title = content.get('title', 'React Documentation')

        # Component examples
        components = metadata.get('components', [])
        for component in components[:3]:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"How do I create a {component} component in React?"},
                    {"role": "assistant", "content": self._extract_component_explanation(component, text)}
                ]
            })

        # Hook examples
        hooks = metadata.get('hooks', [])
        for hook in hooks[:3]:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"How do I use {hook} in React?"},
                    {"role": "assistant", "content": self._extract_hook_explanation(hook, text)}
                ]
            })

        return examples

    def _extract_component_explanation(self, component: str, text: str) -> str:
        """Extract explanation for a component"""
        context = self._extract_context(component, text, 300)
        if context:
            return f"The {component} component {context}"
        return f"The {component} is a React component. Check the documentation for usage details."

    def _extract_hook_explanation(self, hook: str, text: str) -> str:
        """Extract explanation for a React hook"""
        context = self._extract_context(hook, text, 300)
        if context:
            return f"{hook} is a React hook that {context}"
        return f"{hook} is a React hook. Refer to the React documentation for detailed usage."

    def _extract_context(self, term: str, text: str, context_size: int = 200) -> str:
        """Extract context around a term"""
        index = text.lower().find(term.lower())
        if index != -1:
            start = max(0, index - context_size // 2)
            end = min(len(text), index + len(term) + context_size // 2)
            context = text[start:end]
            context = re.sub(r'\s+', ' ', context).strip()
            return context
        return ""


class RustProcessor(DomainProcessor):
    """
    Processor specialized for Rust documentation and code.
    Understands traits, impls, lifetimes, ownership, and Rust patterns.
    """

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self.trait_pattern = re.compile(r'trait\s+([A-Z][a-zA-Z0-9]*)')
        self.impl_pattern = re.compile(r'impl(?:\s+<[^>]+>)?\s+([A-Z][a-zA-Z0-9]*)')
        self.struct_pattern = re.compile(r'struct\s+([A-Z][a-zA-Z0-9]*)')
        self.enum_pattern = re.compile(r'enum\s+([A-Z][a-zA-Z0-9]*)')
        self.fn_pattern = re.compile(r'fn\s+([a-z_][a-zA-Z0-9_]*)')
        self.lifetime_pattern = re.compile(r"'[a-z]+")

    async def process(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """Process Rust content"""
        processed = content.copy()
        text = content.get('content', '')

        # Extract Rust-specific elements
        traits = self.trait_pattern.findall(text)
        impls = self.impl_pattern.findall(text)
        structs = self.struct_pattern.findall(text)
        enums = self.enum_pattern.findall(text)
        functions = self.fn_pattern.findall(text)
        lifetimes = self.lifetime_pattern.findall(text)

        # Extract code blocks
        code_blocks = re.findall(r'```(?:rust|rs)?\n(.*?)```', text, re.DOTALL)

        # Enhance metadata
        metadata = processed.get('metadata', {})
        metadata.update({
            'traits': list(set(traits)),
            'impls': list(set(impls)),
            'structs': list(set(structs)),
            'enums': list(set(enums)),
            'functions': list(set(functions)),
            'uses_lifetimes': len(lifetimes) > 0,
            'has_code': len(code_blocks) > 0,
            'code_count': len(code_blocks)
        })
        processed['metadata'] = metadata

        logger.debug(f"Rust processor found: {len(traits)} traits, {len(structs)} structs, {len(functions)} functions")

        return processed

    def extract_concepts(self, text: str) -> List[str]:
        """Extract Rust-specific concepts"""
        concepts = []

        rust_concepts = {
            'ownership': 'Ownership System',
            'borrowing': 'Borrowing and References',
            'lifetime': 'Lifetimes',
            'trait': 'Traits',
            'generic': 'Generics',
            'macro': 'Macros',
            'async': 'Async Programming',
            'future': 'Futures',
            'error': 'Error Handling',
            'result': 'Result Type',
            'option': 'Option Type',
            'iterator': 'Iterators',
            'closure': 'Closures',
            'smart pointer': 'Smart Pointers',
            'unsafe': 'Unsafe Rust',
            'cargo': 'Cargo Package Manager'
        }

        text_lower = text.lower()
        for keyword, concept in rust_concepts.items():
            if keyword in text_lower:
                concepts.append(concept)

        return list(set(concepts))

    def create_training_examples(self, content: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create Rust-specific training examples"""
        examples = []
        metadata = content.get('metadata', {})
        text = content.get('content', '')
        title = content.get('title', 'Rust Documentation')

        # Trait examples
        traits = metadata.get('traits', [])
        for trait in traits[:2]:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"How do I implement the {trait} trait in Rust?"},
                    {"role": "assistant", "content": self._extract_trait_explanation(trait, text)}
                ]
            })

        # Struct examples
        structs = metadata.get('structs', [])
        for struct in structs[:2]:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"How do I use the {struct} struct in Rust?"},
                    {"role": "assistant", "content": self._extract_struct_explanation(struct, text)}
                ]
            })

        # General documentation
        if text:
            examples.append({
                "messages": [
                    {"role": "user", "content": f"Explain {title}"},
                    {"role": "assistant", "content": text[:2000]}
                ]
            })

        return examples

    def _extract_trait_explanation(self, trait: str, text: str) -> str:
        """Extract explanation for a trait"""
        context = self._extract_context(trait, text, 300)
        if context:
            return f"The {trait} trait {context}"
        return f"The {trait} trait defines behavior in Rust. Check the documentation for implementation details."

    def _extract_struct_explanation(self, struct: str, text: str) -> str:
        """Extract explanation for a struct"""
        context = self._extract_context(struct, text, 300)
        if context:
            return f"The {struct} struct {context}"
        return f"The {struct} is a Rust struct. Refer to the documentation for usage details."

    def _extract_context(self, term: str, text: str, context_size: int = 200) -> str:
        """Extract context around a term"""
        index = text.lower().find(term.lower())
        if index != -1:
            start = max(0, index - context_size // 2)
            end = min(len(text), index + len(term) + context_size // 2)
            context = text[start:end]
            context = re.sub(r'\s+', ' ', context).strip()
            return context
        return ""


# Factory function to get the right processor
def get_domain_processor(domain: str, config: Dict[str, Any] = None) -> Optional[DomainProcessor]:
    """
    Get the appropriate domain processor.

    Args:
        domain: The domain name (drupal, react, rust, etc.)
        config: Optional configuration for the processor

    Returns:
        Domain processor instance or None if domain not supported
    """
    processors = {
        'drupal': DrupalProcessor,
        'react': ReactProcessor,
        'rust': RustProcessor
    }

    processor_class = processors.get(domain.lower())
    if processor_class:
        return processor_class(config)

    logger.warning(f"No processor found for domain: {domain}")
    return None