"""
Domain-specific preprocessors for different knowledge domains
"""

import re
from typing import Dict, List, Any, Optional
import logging
from .base import DataPreprocessor, ProcessedData, DataSource

logger = logging.getLogger(__name__)


class DrupalPreprocessor(DataPreprocessor):
    """
    Specialized preprocessor for Drupal documentation and code.
    Handles Drupal's unique patterns, Symfony integration, and version-specific changes.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.domain = 'drupal'
        self.target_version = self.config.get('target_version', '11')

        # Drupal-specific patterns
        self.patterns = {
            'hooks': r'hook_(\w+)',
            'services': r'@(\w+\.?\w*)',
            'routes': r'\.routing\.yml',
            'entities': r'entity_type:\s*(\w+)',
            'modules': r'\/modules\/(\w+)',
            'themes': r'\/themes\/(\w+)',
            'config': r'\.settings\.yml',
            'twig': r'\{\{.*?\}\}|\{\%.*?\%\}',
            'drupal_class': r'Drupal\\(\w+)\\',
            'version': r'Drupal\s+(\d+(?:\.\d+)?)',
            'deprecated': r'@deprecated|deprecated in drupal:(\d+\.\d+\.\d+)',
        }

        # Version mapping for delta training
        self.version_changes = {
            '7_to_8': {
                'variable_get': 'config',
                'db_query': 'database service',
                'drupal_add_js': 'attach library',
                'l()': 'Link::fromTextAndUrl',
                't()': '->t() or \\Drupal::translation()',
            },
            '8_to_9': {
                'entityManager': 'entityTypeManager',
                'entity.manager': 'entity_type.manager',
                'UrlGeneratorInterface': 'UrlGeneratorInterface (Symfony 4)',
            },
            '9_to_10': {
                'jquery.once': 'core/once',
                'jQuery': 'vanilla JavaScript',
            },
            '10_to_11': {
                'symfony/http-foundation': 'Symfony 6.4',
                'php': 'PHP 8.3+',
            }
        }

    def preprocess(self, raw_data: Dict[str, Any]) -> ProcessedData:
        """Preprocess Drupal-specific content"""
        content = raw_data.get('content', '')
        url = raw_data.get('url', '')

        # Clean content
        content = self.clean_content(content)

        # Extract Drupal-specific elements
        drupal_elements = self._extract_drupal_elements(content)

        # Determine content type
        content_type = self._determine_content_type(url, content)

        # Extract version information
        version_info = self._extract_drupal_version(content)

        # Create processed data
        processed = ProcessedData(
            content=content,
            source=DataSource(
                type=raw_data.get('type', 'documentation'),
                location=url,
                metadata=raw_data.get('metadata', {}),
                version=version_info.get('version')
            ),
            format='instruction' if content_type == 'api' else 'conversation',
            metadata={
                'domain': 'drupal',
                'content_type': content_type,
                'drupal_elements': drupal_elements,
                'target_version': self.target_version
            },
            version_info=version_info
        )

        # Apply delta strategy if migrating versions
        if self.enable_versioning and version_info:
            processed = self._apply_drupal_delta_strategy(processed)

        return processed

    def _extract_drupal_elements(self, content: str) -> Dict[str, List[str]]:
        """Extract Drupal-specific code elements"""
        elements = {
            'hooks': [],
            'services': [],
            'entities': [],
            'modules': [],
            'drupal_classes': [],
            'twig_templates': []
        }

        # Find hooks
        for match in re.finditer(self.patterns['hooks'], content):
            hook_name = f"hook_{match.group(1)}"
            if hook_name not in elements['hooks']:
                elements['hooks'].append(hook_name)

        # Find services
        for match in re.finditer(self.patterns['services'], content):
            service = match.group(1)
            if service not in elements['services']:
                elements['services'].append(service)

        # Find Drupal classes/namespaces
        for match in re.finditer(self.patterns['drupal_class'], content):
            namespace = match.group(1)
            if namespace not in elements['drupal_classes']:
                elements['drupal_classes'].append(namespace)

        # Find entities
        for match in re.finditer(self.patterns['entities'], content):
            entity = match.group(1)
            if entity not in elements['entities']:
                elements['entities'].append(entity)

        return elements

    def _determine_content_type(self, url: str, content: str) -> str:
        """Determine the type of Drupal content"""
        url_lower = url.lower()
        content_lower = content.lower()

        if 'api.drupal.org' in url_lower or '/api/' in url_lower:
            return 'api'
        elif 'change-records' in url_lower or 'change record' in content_lower:
            return 'change_record'
        elif '/docs/user_guide' in url_lower:
            return 'user_guide'
        elif 'module' in url_lower or 'module development' in content_lower:
            return 'module_development'
        elif 'theme' in url_lower or 'theming' in content_lower:
            return 'theming'
        elif any(pattern in content_lower for pattern in ['migration', 'upgrade', 'update']):
            return 'migration'
        else:
            return 'general'

    def _extract_drupal_version(self, content: str) -> Dict[str, Any]:
        """Extract Drupal version information"""
        version_info = {
            'version': None,
            'deprecated_in': [],
            'introduced_in': [],
            'removed_in': []
        }

        # Find main version mentions
        for match in re.finditer(self.patterns['version'], content):
            version = match.group(1)
            if not version_info['version']:
                version_info['version'] = version

        # Find deprecation notices
        for match in re.finditer(self.patterns['deprecated'], content):
            if match.group(1):  # Has version number
                version_info['deprecated_in'].append(match.group(1))

        # Look for "new in" or "introduced in" patterns
        new_pattern = r'(?:new|introduced|added)\s+in\s+(?:drupal[:\s]+)?(\d+(?:\.\d+)?)'
        for match in re.finditer(new_pattern, content, re.IGNORECASE):
            version_info['introduced_in'].append(match.group(1))

        # Look for "removed in" patterns
        removed_pattern = r'removed\s+in\s+(?:drupal[:\s]+)?(\d+(?:\.\d+)?)'
        for match in re.finditer(removed_pattern, content, re.IGNORECASE):
            version_info['removed_in'].append(match.group(1))

        return version_info

    def _apply_drupal_delta_strategy(self, data: ProcessedData) -> ProcessedData:
        """Apply Drupal-specific delta training strategy"""
        version = data.version_info.get('version')
        if not version:
            return data

        # Determine if content is for old vs new version
        try:
            version_num = float(version.split('.')[0])
            target_num = float(self.target_version.split('.')[0])

            if version_num < target_num:
                # Old version content - mark as deprecated example
                data.content = f"[DEPRECATED - Drupal {version}]\n{data.content}\n[Use Drupal {self.target_version} patterns instead]"
                data.training_weight = 0.5  # Lower weight for old patterns
            elif version_num == target_num:
                # Current version - emphasize
                data.content = f"[CURRENT - Drupal {self.target_version}]\n{data.content}"
                data.training_weight = 1.5  # Higher weight for current patterns
            else:
                # Future version - mark as preview
                data.content = f"[PREVIEW - Drupal {version}]\n{data.content}"
                data.training_weight = 0.8
        except (ValueError, IndexError):
            pass

        # Add migration notes if content contains old patterns
        migration_notes = self._generate_migration_notes(data.content)
        if migration_notes:
            data.metadata['migration_notes'] = migration_notes

        return data

    def _generate_migration_notes(self, content: str) -> List[str]:
        """Generate migration notes for old patterns"""
        notes = []

        # Check for old patterns and suggest replacements
        for version_key, changes in self.version_changes.items():
            for old_pattern, new_pattern in changes.items():
                if old_pattern in content:
                    notes.append(f"Replace '{old_pattern}' with '{new_pattern}'")

        return notes


class CodebasePreprocessor(DataPreprocessor):
    """
    Preprocessor for software codebases and libraries.
    Handles code documentation, examples, and API references.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.language = self.config.get('language', 'python')
        self.framework = self.config.get('framework')

        # Language-specific patterns
        self.patterns = {
            'python': {
                'function': r'def\s+(\w+)\s*\(',
                'class': r'class\s+(\w+)',
                'import': r'(?:from\s+[\w.]+\s+)?import\s+[\w.,\s]+',
                'decorator': r'@(\w+)',
                'docstring': r'""".*?"""',
            },
            'javascript': {
                'function': r'(?:function\s+(\w+)|const\s+(\w+)\s*=\s*(?:async\s+)?\()',
                'class': r'class\s+(\w+)',
                'import': r'import\s+.*?from\s+[\'"].*?[\'"]',
                'export': r'export\s+(?:default\s+)?',
                'react_component': r'(?:function|const)\s+(\w+)\s*\([^)]*\)\s*\{[\s\S]*?return\s*\(?[\s\S]*?<',
            },
            'php': {
                'function': r'function\s+(\w+)\s*\(',
                'class': r'class\s+(\w+)',
                'namespace': r'namespace\s+([\w\\]+)',
                'use': r'use\s+([\w\\]+)',
            }
        }

    def preprocess(self, raw_data: Dict[str, Any]) -> ProcessedData:
        """Preprocess code and technical documentation"""
        content = raw_data.get('content', '')
        url = raw_data.get('url', '')

        # Clean content
        content = self.clean_content(content)

        # Extract code elements based on language
        code_elements = self._extract_code_elements(content)

        # Identify code blocks and examples
        code_blocks = self._extract_code_blocks(content)

        # Determine documentation type
        doc_type = self._determine_doc_type(content, code_blocks)

        processed = ProcessedData(
            content=content,
            source=DataSource(
                type='code_documentation',
                location=url,
                metadata=raw_data.get('metadata', {})
            ),
            format='instruction' if doc_type == 'api' else 'conversation',
            metadata={
                'language': self.language,
                'framework': self.framework,
                'code_elements': code_elements,
                'code_blocks': code_blocks,
                'doc_type': doc_type
            }
        )

        return processed

    def _extract_code_elements(self, content: str) -> Dict[str, List[str]]:
        """Extract code elements based on language"""
        elements = {
            'functions': [],
            'classes': [],
            'imports': []
        }

        patterns = self.patterns.get(self.language, self.patterns['python'])

        # Extract functions
        if 'function' in patterns:
            for match in re.finditer(patterns['function'], content):
                func_name = match.group(1) or match.group(2) if len(match.groups()) > 1 else match.group(1)
                if func_name and func_name not in elements['functions']:
                    elements['functions'].append(func_name)

        # Extract classes
        if 'class' in patterns:
            for match in re.finditer(patterns['class'], content):
                class_name = match.group(1)
                if class_name not in elements['classes']:
                    elements['classes'].append(class_name)

        return elements

    def _extract_code_blocks(self, content: str) -> List[Dict[str, str]]:
        """Extract code blocks from markdown or documentation"""
        code_blocks = []

        # Markdown code blocks
        pattern = r'```(\w*)\n(.*?)```'
        for match in re.finditer(pattern, content, re.DOTALL):
            code_blocks.append({
                'language': match.group(1) or self.language,
                'code': match.group(2).strip()
            })

        return code_blocks

    def _determine_doc_type(self, content: str, code_blocks: List[Dict]) -> str:
        """Determine the type of documentation"""
        content_lower = content.lower()

        if 'api reference' in content_lower or 'api documentation' in content_lower:
            return 'api'
        elif len(code_blocks) > 3:
            return 'tutorial'
        elif 'example' in content_lower or 'how to' in content_lower:
            return 'example'
        elif 'class' in content_lower and 'method' in content_lower:
            return 'class_reference'
        else:
            return 'general'


class MarkdownPreprocessor(DataPreprocessor):
    """
    General preprocessor for markdown documentation.
    Preserves structure and formatting while extracting key information.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.preserve_structure = self.config.get('preserve_structure', True)
        self.extract_toc = self.config.get('extract_toc', True)

    def preprocess(self, raw_data: Dict[str, Any]) -> ProcessedData:
        """Preprocess markdown documentation"""
        content = raw_data.get('content', '')

        # Clean while preserving markdown structure
        content = self._clean_markdown(content)

        # Extract table of contents
        toc = self._extract_toc(content) if self.extract_toc else []

        # Extract metadata from frontmatter
        metadata = self._extract_frontmatter(content)

        # Split into sections
        sections = self._split_sections(content)

        processed = ProcessedData(
            content=content,
            source=DataSource(
                type='markdown',
                location=raw_data.get('url', ''),
                metadata=raw_data.get('metadata', {})
            ),
            format='conversation',
            metadata={
                'toc': toc,
                'sections': sections,
                'frontmatter': metadata,
                'has_code': '```' in content,
                'has_tables': '|' in content and '---' in content
            }
        )

        return processed

    def _clean_markdown(self, content: str) -> str:
        """Clean markdown while preserving structure"""
        # Remove excessive blank lines
        content = re.sub(r'\n{3,}', '\n\n', content)

        # Normalize header formatting
        content = re.sub(r'^(#+)\s*', r'\1 ', content, flags=re.MULTILINE)

        # Fix list formatting
        content = re.sub(r'^(\s*)([-*+])\s+', r'\1\2 ', content, flags=re.MULTILINE)

        return content.strip()

    def _extract_toc(self, content: str) -> List[Dict[str, Any]]:
        """Extract table of contents from headers"""
        toc = []
        header_pattern = r'^(#{1,6})\s+(.+)$'

        for match in re.finditer(header_pattern, content, re.MULTILINE):
            level = len(match.group(1))
            title = match.group(2).strip()
            toc.append({
                'level': level,
                'title': title,
                'anchor': self._slugify(title)
            })

        return toc

    def _extract_frontmatter(self, content: str) -> Dict[str, Any]:
        """Extract YAML frontmatter if present"""
        metadata = {}

        if content.startswith('---'):
            pattern = r'^---\s*\n(.*?)\n---'
            match = re.match(pattern, content, re.DOTALL)
            if match:
                # Parse YAML (simplified)
                frontmatter = match.group(1)
                for line in frontmatter.split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        metadata[key.strip()] = value.strip()

        return metadata

    def _split_sections(self, content: str) -> List[Dict[str, str]]:
        """Split content into sections based on headers"""
        sections = []
        current_section = {'title': 'Introduction', 'content': '', 'level': 0}

        for line in content.split('\n'):
            if line.startswith('#'):
                # Save previous section if it has content
                if current_section['content']:
                    sections.append(current_section)

                # Start new section
                match = re.match(r'^(#+)\s+(.+)$', line)
                if match:
                    current_section = {
                        'title': match.group(2),
                        'content': '',
                        'level': len(match.group(1))
                    }
            else:
                current_section['content'] += line + '\n'

        # Add last section
        if current_section['content']:
            sections.append(current_section)

        return sections

    def _slugify(self, text: str) -> str:
        """Convert text to URL-friendly slug"""
        # Remove special characters and convert to lowercase
        slug = re.sub(r'[^\w\s-]', '', text.lower())
        # Replace spaces with hyphens
        slug = re.sub(r'[-\s]+', '-', slug)
        return slug