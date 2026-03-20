# 📚 Data Preparation Guide for LLM Training

## Overview

Brain From Cero includes a **comprehensive data preparation system** that automates the collection, preprocessing, and formatting of training data from various sources. This modular system is designed to handle domain-specific knowledge preparation with special support for versioning and delta training strategies.

---

## 🎯 Key Features

### Modular Architecture
- **Collectors**: Web scraping, documentation crawling, API docs, change records
- **Preprocessors**: Domain-specific processing (Drupal, code, markdown)
- **Formatters**: Multiple training formats (JSONL, instruction, conversation, delta)
- **Pipeline Orchestration**: Complete workflow automation

### Advanced Capabilities
- **Delta Training Strategy**: Version-aware training with emphasis on changes
- **Intelligent Scraping**: Respects robots.txt, rate limiting, caching
- **Content Extraction**: HTML to Markdown conversion with structure preservation
- **Batch Processing**: Handle multiple domains in parallel

---

## 🔄 Complete Workflow

### Step 1: Choose Your Data Sources

```python
from brain.training.data_preparation import DataSource

sources = [
    DataSource(
        type='documentation',
        location='https://drupal.org/docs/user_guide',
        metadata={'category': 'user_guide'},
        version='11'
    ),
    DataSource(
        type='api_doc',
        location='https://api.drupal.org/api/drupal/11',
        metadata={'category': 'api_reference'}
    )
]
```

### Step 2: Configure the Pipeline

```python
from brain.training.data_preparation import DataPreparationPipeline

pipeline = DataPreparationPipeline({
    'output_dir': '/path/to/output',
    'cache_hours': 24,
    'rate_limit': 1.0  # seconds between requests
})

pipeline.configure(
    collector_type='documentation',
    preprocessor_type='drupal',
    formatter_type='delta',
    target_version='11',
    enable_versioning=True
)
```

### Step 3: Run Data Preparation

```python
# Prepare the data
output_file = await pipeline.prepare_data(sources)

# Check statistics
print(f"Collected: {pipeline.stats['items_collected']} items")
print(f"Processed: {pipeline.stats['items_preprocessed']} items")
print(f"Formatted: {pipeline.stats['items_formatted']} items")
```

---

## 📊 Data Collectors

### WebScraper
General-purpose web scraper with intelligent content extraction.

```python
from brain.training.data_preparation.collectors import WebScraper

scraper = WebScraper({
    'rate_limit': 1.0,
    'follow_links': True,
    'max_depth': 3,
    'allowed_domains': ['example.com']
})

data = await scraper.collect(DataSource(
    type='url',
    location='https://example.com/docs'
))
```

### DocumentationCrawler
Specialized for documentation sites with navigation trees.

```python
from brain.training.data_preparation.collectors import DocumentationCrawler

crawler = DocumentationCrawler({
    'max_pages': 100,
    'sitemap_patterns': ['sitemap.xml', 'llms.txt']
})

# Collect from sitemap
data = await crawler.collect(DataSource(
    type='sitemap',
    location='https://drupal.org/sitemap.xml'
))
```

### APIDocScraper
Extracts API documentation with code examples.

```python
from brain.training.data_preparation.collectors import APIDocScraper

api_scraper = APIDocScraper()

data = await api_scraper.collect(DataSource(
    type='api_doc',
    location='https://api.drupal.org/api/drupal/11'
))

# Extracted elements available in metadata
for item in data:
    api_elements = item['metadata']['api_elements']
    print(f"Functions: {api_elements['functions']}")
    print(f"Classes: {api_elements['classes']}")
    print(f"Code examples: {len(api_elements['code_examples'])}")
```

### ChangeRecordCollector
Critical for version-specific training.

```python
from brain.training.data_preparation.collectors import ChangeRecordCollector

change_collector = ChangeRecordCollector()

data = await change_collector.collect(DataSource(
    type='changes',
    location='https://drupal.org/list-changes/drupal'
))

# Version information in metadata
for item in data:
    version_info = item['metadata']['version_info']
    print(f"Versions: {version_info['versions_mentioned']}")
    print(f"Deprecated: {len(version_info['deprecated_items'])}")
    print(f"New features: {len(version_info['new_features'])}")
```

---

## 🔧 Domain-Specific Preprocessors

### DrupalPreprocessor
Handles Drupal's unique patterns and Symfony integration.

```python
from brain.training.data_preparation.preprocessors import DrupalPreprocessor

preprocessor = DrupalPreprocessor({
    'target_version': '11',
    'enable_versioning': True
})

processed = preprocessor.preprocess(raw_data)

# Drupal elements extracted
elements = processed.metadata['drupal_elements']
print(f"Hooks: {elements['hooks']}")
print(f"Services: {elements['services']}")
print(f"Entities: {elements['entities']}")
```

**Features:**
- Extracts hooks, services, entities, modules
- Version migration mapping (D7→D8→D9→D10→D11)
- Deprecation detection and marking
- Delta training strategy application

### CodebasePreprocessor
For software libraries and codebases.

```python
from brain.training.data_preparation.preprocessors import CodebasePreprocessor

preprocessor = CodebasePreprocessor({
    'language': 'python',
    'framework': 'django'
})

processed = preprocessor.preprocess(raw_data)

# Code elements extracted
elements = processed.metadata['code_elements']
print(f"Functions: {elements['functions']}")
print(f"Classes: {elements['classes']}")
```

**Supported Languages:**
- Python (Django, Flask, FastAPI)
- JavaScript (React, Vue, Angular)
- PHP (Laravel, Symfony)

### MarkdownPreprocessor
General markdown documentation processing.

```python
from brain.training.data_preparation.preprocessors import MarkdownPreprocessor

preprocessor = MarkdownPreprocessor({
    'preserve_structure': True,
    'extract_toc': True
})

processed = preprocessor.preprocess(raw_data)

# Table of contents extracted
toc = processed.metadata['toc']
for item in toc:
    print(f"{'  ' * (item['level']-1)}- {item['title']}")
```

---

## 📝 Training Formatters

### JSONLFormatter
Standard format for LLM fine-tuning.

```python
from brain.training.data_preparation.formatters import JSONLFormatter

formatter = JSONLFormatter({
    'max_length': 2048,
    'include_metadata': True
})

formatted = formatter.format(processed_data)

# Output structure:
# {
#     "messages": [
#         {"role": "system", "content": "..."},
#         {"role": "user", "content": "..."},
#         {"role": "assistant", "content": "..."}
#     ],
#     "metadata": {...},
#     "weight": 1.0
# }
```

### InstructionFormatter
For instruction-tuning datasets.

```python
from brain.training.data_preparation.formatters import InstructionFormatter

formatter = InstructionFormatter({
    'instruction_templates': {
        'explain': "Explain the following concept: {topic}",
        'implement': "Write code to implement: {task}"
    }
})

formatted = formatter.format(processed_data)

# Output structure:
# {
#     "instruction": "Explain how to use the hook_menu function",
#     "context": "Example code: ...",
#     "response": "The hook_menu function...",
#     "metadata": {...}
# }
```

### ConversationFormatter
Multi-turn dialogue format.

```python
from brain.training.data_preparation.formatters import ConversationFormatter

formatter = ConversationFormatter({
    'personas': {
        'expert': "You are an expert in {domain} with deep knowledge of {topic}"
    },
    'max_turns': 5
})

formatted = formatter.format(processed_data)

# Creates realistic conversation flows
```

### DeltaTrainingFormatter
Version-aware training with emphasis on changes.

```python
from brain.training.data_preparation.formatters import DeltaTrainingFormatter

formatter = DeltaTrainingFormatter({
    'emphasis_old_way': True,
    'include_migration': True
})

formatted = formatter.format(processed_data)

# Output includes version context and training weights:
# {
#     "messages": [...],
#     "version_context": {
#         "from": "10.0",
#         "to": "11.0",
#         "is_breaking_change": true
#     },
#     "weight": 1.5  # Higher weight for important changes
# }
```

---

## 🚀 Quick Start Examples

### Example 1: Prepare Drupal Training Data

```python
import asyncio
from brain.training.data_preparation import DataPreparationPipeline

async def prepare_drupal():
    pipeline = DataPreparationPipeline()

    # Use built-in Drupal preparation
    output_file = await pipeline.prepare_drupal_training_data(
        target_version="11",
        include_change_records=True
    )

    print(f"Training data saved to: {output_file}")

asyncio.run(prepare_drupal())
```

### Example 2: Custom Domain Preparation

```python
async def prepare_react():
    pipeline = DataPreparationPipeline()

    sources = [
        {
            'type': 'documentation',
            'location': 'https://react.dev/learn'
        },
        {
            'type': 'api_doc',
            'location': 'https://react.dev/reference'
        }
    ]

    output_file = await pipeline.prepare_custom_domain_data(
        domain='react',
        sources=sources,
        language='javascript',
        framework='react'
    )

    print(f"React training data saved to: {output_file}")

asyncio.run(prepare_react())
```

### Example 3: Batch Processing Multiple Domains

```python
from brain.training.data_preparation import BatchProcessor

async def prepare_multiple():
    processor = BatchProcessor({
        'max_concurrent': 3
    })

    batch_configs = [
        {
            'domain': 'drupal',
            'version': '11'
        },
        {
            'domain': 'react',
            'sources': [
                {'type': 'url', 'location': 'https://react.dev/learn'}
            ],
            'options': {
                'language': 'javascript'
            }
        },
        {
            'domain': 'python',
            'sources': [
                {'type': 'documentation', 'location': 'https://docs.python.org/3/'}
            ]
        }
    ]

    results = await processor.process_batch(batch_configs)
    print(f"Prepared {len(results)} datasets")

asyncio.run(prepare_multiple())
```

---

## 🌐 API Endpoints

### Prepare Training Data
```bash
POST /agents/{agent_id}/training/prepare
```

```json
{
  "sources": [
    {
      "type": "documentation",
      "location": "https://example.com/docs",
      "metadata": {"category": "main"}
    }
  ],
  "config": {
    "collector_type": "web",
    "preprocessor_type": "markdown",
    "formatter_type": "jsonl",
    "follow_links": true,
    "max_pages": 100
  }
}
```

### Prepare Drupal Data (Specialized)
```bash
POST /agents/{agent_id}/training/prepare/drupal
```

```json
{
  "target_version": "11",
  "include_change_records": true,
  "max_pages": 100
}
```

### Batch Preparation
```bash
POST /agents/{agent_id}/training/prepare/batch
```

```json
{
  "batch_configs": [
    {"domain": "drupal", "version": "11"},
    {"domain": "react", "sources": [...]}
  ],
  "max_concurrent": 3
}
```

### Check Preparation Status
```bash
GET /training/prepare/{job_id}
```

Response:
```json
{
  "job_id": "...",
  "status": "collecting",
  "progress": 0.45,
  "items_collected": 150,
  "items_preprocessed": 120,
  "items_formatted": 100,
  "errors": []
}
```

---

## 💡 Best Practices

### 1. Data Quality
- **Curate Sources**: Choose authoritative, up-to-date documentation
- **Version Awareness**: Always specify versions for consistency
- **Change Records**: Include migration guides for version-specific training

### 2. Performance Optimization
- **Caching**: Use cache to avoid re-scraping (default: 24 hours)
- **Rate Limiting**: Respect server limits (default: 1 second between requests)
- **Batch Processing**: Process multiple domains in parallel

### 3. Delta Training Strategy
```python
# Example: Emphasize version differences
pipeline.configure(
    formatter_type='delta',
    target_version='11',
    enable_versioning=True
)

# This will:
# - Mark deprecated patterns with lower weight (0.5x)
# - Emphasize current patterns with higher weight (1.5x)
# - Include migration notes in training data
```

### 4. Content Chunking
For large documents, use chunking:
```python
preprocessor = MarkdownPreprocessor()
chunks = preprocessor.chunk_content(
    content,
    chunk_size=1024,
    overlap=128  # Overlap prevents context loss
)
```

---

## 🔧 Extending the System

### Custom Collector
```python
from brain.training.data_preparation.base import DataCollector

class MyCustomCollector(DataCollector):
    async def collect(self, source: DataSource) -> List[Dict[str, Any]]:
        # Your collection logic
        data = await fetch_from_custom_source(source.location)

        # Cache if needed
        self.cache_data(source, data)

        return data
```

### Custom Preprocessor
```python
from brain.training.data_preparation.base import DataPreprocessor

class MyDomainPreprocessor(DataPreprocessor):
    def preprocess(self, raw_data: Dict[str, Any]) -> ProcessedData:
        # Extract domain-specific patterns
        content = self.clean_content(raw_data['content'])

        # Apply domain logic
        processed = ProcessedData(
            content=content,
            source=DataSource(...),
            format='instruction',
            metadata={'domain': 'my_domain'}
        )

        return processed
```

### Custom Formatter
```python
from brain.training.data_preparation.base import DataFormatter

class MyCustomFormatter(DataFormatter):
    def format(self, data: ProcessedData) -> Dict[str, Any]:
        # Format for your training needs
        return {
            "custom_field": data.content,
            "metadata": data.metadata
        }
```

---

## 📊 Monitoring & Statistics

The pipeline provides detailed statistics:

```python
stats = pipeline.stats
print(f"""
Data Preparation Statistics:
- Sources processed: {stats['sources_processed']}
- Items collected: {stats['items_collected']}
- Items preprocessed: {stats['items_preprocessed']}
- Items formatted: {stats['items_formatted']}
- Errors: {len(stats['errors'])}
- Duration: {stats['duration_seconds']}s
""")
```

Statistics are also saved alongside output:
```bash
training_data_20240101.jsonl
training_data_20240101.stats.json  # Pipeline statistics
```

---

## ✅ Success Checklist

- [ ] Identified target domain and version
- [ ] Selected appropriate data sources
- [ ] Configured pipeline components
- [ ] Set rate limiting and caching
- [ ] Enabled versioning if needed
- [ ] Ran preparation pipeline
- [ ] Verified output quality
- [ ] Used prepared data for training

---

## 📚 Additional Resources

- [Agent Training Guide](AGENT_TRAINING_GUIDE.md)
- [LoRA Training Architecture](../LORA_TRAINING_ARCHITECTURE.md)
- [API Documentation](http://localhost:8000/docs#/data-preparation)

---

**Happy Data Preparation! 🎉**

Transform any knowledge domain into high-quality training data!