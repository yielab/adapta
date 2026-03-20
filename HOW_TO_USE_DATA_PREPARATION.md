# 🎯 How to Use Data Preparation in Brain Platform

## ⚠️ Current Status

The Data Preparation functionality is **fully implemented in the backend** but:
- ❌ **NOT exposed in the Dashboard UI**
- ❌ **NOT available via CLI commands**
- ⚠️ **API endpoints exist but may not be properly mounted**

## 📍 Where the Data Preparation Code Lives

### Core Implementation
```
brain/training/data_preparation/
├── __init__.py           # Main module exports
├── base.py               # Base classes and interfaces
├── collectors.py         # Data collection implementations
│   ├── WebScraper
│   ├── DocumentationCrawler
│   ├── APIDocScraper
│   └── ChangeRecordCollector
├── preprocessors.py      # Domain-specific preprocessing
│   ├── DrupalPreprocessor
│   ├── CodebasePreprocessor
│   └── MarkdownPreprocessor
├── formatters.py         # Output formatting
│   ├── JSONLFormatter
│   ├── InstructionFormatter
│   ├── ConversationFormatter
│   └── DeltaFormatter
└── pipeline.py          # Main orchestration pipeline
```

### API Implementation
- **Location**: `brain/api/data_preparation.py`
- **Endpoints** (should be available but may not be working):
  - `POST /v1/agents/{agent_id}/training/prepare`
  - `POST /v1/agents/{agent_id}/training/prepare/drupal`
  - `POST /v1/agents/{agent_id}/training/prepare/batch`
  - `GET /v1/training/prepare/{job_id}`
  - `GET /v1/training/prepare/examples`

## 🚀 How to Access Data Preparation Features

### Option 1: Direct Python Usage (Recommended)

Since the API endpoints aren't working properly, you can use the data preparation directly via Python:

```python
# 1. Enter the Docker container
docker exec -it brain-server bash

# 2. Start Python
python3

# 3. Use the data preparation pipeline
from brain.training.data_preparation import DataPreparationPipeline, DataSource
import asyncio

async def prepare_data():
    # Create pipeline
    pipeline = DataPreparationPipeline({
        'output_dir': '/app/data/training_data',
        'cache_hours': 24,
        'rate_limit': 1.0
    })

    # Configure for your use case
    pipeline.configure(
        collector_type='web',        # or 'documentation', 'api', 'changes'
        preprocessor_type='markdown', # or 'drupal', 'code'
        formatter_type='jsonl',       # or 'instruction', 'conversation', 'delta'
    )

    # Define sources
    sources = [
        DataSource(
            type='url',
            location='https://example.com/docs',
            metadata={'category': 'documentation'}
        )
    ]

    # Run preparation
    output_file = await pipeline.prepare_data(sources)
    print(f"Data prepared: {output_file}")
    print(f"Stats: {pipeline.stats}")
    return output_file

# Run it
result = asyncio.run(prepare_data())
```

### Option 2: Create a Custom Script

Create a file `prepare_training_data.py`:

```python
#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

# Add Brain to path
sys.path.insert(0, '/app')

from brain.training.data_preparation import (
    DataPreparationPipeline,
    DataSource,
    WebScraper,
    DocumentationCrawler,
    DrupalPreprocessor,
    JSONLFormatter
)

async def main():
    # Example: Prepare Drupal documentation for training
    pipeline = DataPreparationPipeline({
        'output_dir': '/app/data/training_data',
        'cache_hours': 24,
        'rate_limit': 1.0
    })

    # Configure for Drupal
    pipeline.configure(
        collector_type='documentation',
        preprocessor_type='drupal',
        formatter_type='delta',  # For version-aware training
        target_version='11',
        enable_versioning=True
    )

    # Drupal 11 sources
    sources = [
        DataSource(
            type='documentation',
            location='https://www.drupal.org/docs/user_guide',
            version='11',
            metadata={'category': 'user_guide'}
        ),
        DataSource(
            type='changes',
            location='https://www.drupal.org/list-changes/drupal',
            version='11',
            metadata={'category': 'change_records'}
        )
    ]

    # Process
    output = await pipeline.prepare_data(sources)
    print(f"✅ Training data saved to: {output}")

    # Show statistics
    print("\n📊 Statistics:")
    for key, value in pipeline.stats.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    asyncio.run(main())
```

Run it inside the container:
```bash
docker exec -it brain-server python3 /path/to/prepare_training_data.py
```

### Option 3: Fix the API Endpoints (For Developers)

The issue is likely in `brain/api/app.py`. Check that the data_preparation router is properly included:

```python
# In brain/api/app.py
app.include_router(data_prep_router.router, prefix="", tags=["data-preparation"])
```

## 📚 Available Data Preparation Components

### Collectors
1. **WebScraper** - General web scraping
2. **DocumentationCrawler** - Documentation sites
3. **APIDocScraper** - API documentation
4. **ChangeRecordCollector** - Version change records

### Preprocessors
1. **DrupalPreprocessor** - Drupal-specific processing
2. **CodebasePreprocessor** - Source code processing
3. **MarkdownPreprocessor** - Markdown content

### Formatters
1. **JSONLFormatter** - Standard JSONL format
2. **InstructionFormatter** - Instruction-following format
3. **ConversationFormatter** - Conversational format
4. **DeltaFormatter** - Delta/version-aware format

## 🎯 Common Use Cases

### 1. Scrape Website for Training Data
```python
sources = [DataSource(type='url', location='https://docs.example.com')]
pipeline.configure(collector_type='web', preprocessor_type='markdown', formatter_type='jsonl')
```

### 2. Prepare Drupal 11 Training Data
```python
sources = [DataSource(type='documentation', location='https://drupal.org/docs', version='11')]
pipeline.configure(collector_type='documentation', preprocessor_type='drupal', formatter_type='delta')
```

### 3. Process API Documentation
```python
sources = [DataSource(type='api_doc', location='https://api.example.com/docs')]
pipeline.configure(collector_type='api', preprocessor_type='code', formatter_type='instruction')
```

## 📋 Next Steps

To make data preparation more accessible:

1. **Fix API Endpoints** - Debug why they're not mounted properly
2. **Add CLI Commands** - Create brain CLI commands for data prep
3. **Add UI Components** - Add data preparation tab to dashboard
4. **Create Examples** - Add example scripts in `/examples` directory
5. **Test Integration** - Ensure end-to-end workflow works

## 📖 Full Documentation

See `/home/ox/Sites/brainFromCero/docs/guides/DATA_PREPARATION_GUIDE.md` for complete documentation.

---

**Note**: The data preparation system is powerful but currently requires direct Python usage or API calls. The UI integration is not yet implemented.