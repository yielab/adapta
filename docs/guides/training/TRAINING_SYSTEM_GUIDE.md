# Brain Platform Training System Guide

## Overview

The Brain platform includes a professional-grade training system for data preparation and model fine-tuning. This guide covers the complete training pipeline from data collection to model deployment.

## System Architecture

The training system consists of:

1. **Data Collection Pipeline**
   - Professional web scraper with multi-algorithm extraction
   - Documentation crawler for comprehensive site coverage
   - File-based data ingestion
   - Domain-specific collectors (Drupal, React, Rust)

2. **Data Validation System**
   - 4-dimensional quality scoring
   - Content deduplication via MD5 hashing
   - Token counting and validation
   - Domain-specific validation rules

3. **Data Preprocessing**
   - Domain-specific processors
   - Content normalization
   - Format standardization
   - Metadata extraction

4. **Training Infrastructure**
   - LoRA fine-tuning support
   - Multi-GPU training capability
   - Automatic checkpointing
   - Model evaluation metrics

## Quick Start

### 1. Using the Dashboard

Access the training interface at `http://localhost:8000/dashboard/`

The dashboard provides three main data collection methods:

#### Web Scraping (Column 1)
- Enter URLs to scrape (one per line)
- Select domain type (Drupal, React, Rust, Custom)
- Set quality threshold (0.0-1.0)
- Click "Start Web Scraping"

#### Drupal Data Collection (Column 2)
- Enter Drupal site URL
- Provide API endpoint if available
- Configure collection depth
- Click "Start Drupal Collection"

#### File Upload (Column 3)
- Upload JSON/JSONL training data
- Supports conversation format
- Automatic validation
- Click "Upload File"

### 2. Using the CLI

```bash
# Basic web scraping
brain collect web --urls https://example.com --domain drupal

# Drupal-specific collection
brain collect drupal --site https://drupal.org --depth 100

# File-based collection
brain collect file --path /path/to/data.json

# Start training
brain train start --model llama2 --data prepared_data/
```

### 3. Using the API

```python
import requests

# Web scraping
response = requests.post('http://localhost:8000/api/prepare-data', json={
    'source': 'web_scraping',
    'config': {
        'urls': ['https://example.com'],
        'domain': 'drupal',
        'quality_threshold': 0.75
    }
})

# Check job status
job_id = response.json()['job_id']
status = requests.get(f'http://localhost:8000/api/job-status/{job_id}')
```

## Domain Configurations

### Drupal
```yaml
min_examples: 50
min_tokens: 5000
quality_threshold: 0.75
required_keywords: [module, hook, api, drupal]
technical_terms: [hook_*, theme_*, render, entity, field]
```

### React
```yaml
min_examples: 30
min_tokens: 3000
quality_threshold: 0.75
required_keywords: [component, jsx, react, hook]
technical_terms: [useState, useEffect, props, render]
```

### Rust
```yaml
min_examples: 40
min_tokens: 4000
quality_threshold: 0.75
required_keywords: [trait, impl, cargo, rust]
technical_terms: [lifetime, borrow, mut, async, tokio]
```

### Custom
```yaml
min_examples: 10
min_tokens: 500
quality_threshold: 0.60
# No required keywords for custom domain
```

## Quality Scoring System

The system uses a 4-dimensional quality scoring system:

1. **Technical Depth (30%)**
   - Code block presence and quality
   - Technical term density
   - API reference count
   - Documentation structure

2. **Completeness (25%)**
   - Token count relative to minimum
   - Section organization
   - Example coverage
   - Cross-references

3. **Relevance (20%)**
   - Domain keyword presence
   - Topic consistency
   - Context appropriateness

4. **Base Score (25%)**
   - Valid content structure
   - Proper formatting
   - Readable text
   - Minimal noise

## Data Flow

```
1. Collection → Raw data ingested from sources
2. Validation → Quality checks and deduplication
3. Preprocessing → Domain-specific processing
4. Formatting → Convert to training format
5. Final Validation → Ensure training readiness
6. Training → Fine-tune model with prepared data
```

## Troubleshooting

### Common Issues

1. **Low Quality Scores**
   - Check if content matches domain requirements
   - Verify URLs are documentation-heavy
   - Increase collection depth for sitemaps

2. **Collection Failures**
   - Verify network connectivity
   - Check if sites require authentication
   - Review rate limiting settings

3. **Validation Errors**
   - Ensure minimum token count is met
   - Check for duplicate content
   - Verify JSON format is correct

### Debug Mode

Enable debug output for detailed logs:

```python
config = {
    'debug': True,
    'export_metrics': True,
    'log_level': 'DEBUG'
}
```

Debug files are saved to:
- `debug_collection_metrics.json`
- `debug_quality_scores.json`
- `debug_extractor_stats.json`

## Performance Metrics

### Target Metrics
- Collection Success Rate: 95%+
- Average Quality Score: 0.85+
- Duplicate Rate: <1%
- Processing Speed: <2s per page
- Token Generation: 50K-100K per domain

### Current Performance
- Drupal.org: ~150-250 pages collected
- Quality Score: 0.75-0.90 average
- Token Output: 50K-100K tokens
- Success Rate: 95%+ with fallback

## Advanced Features

### Batch Processing
```python
# Process multiple URLs in parallel
urls = ['url1', 'url2', 'url3', ...]
config = {
    'batch_size': 10,
    'max_workers': 5,
    'timeout': 30
}
```

### Custom Extractors
```python
# Add custom extraction logic
class CustomExtractor:
    def extract(self, html, url):
        # Custom extraction logic
        return content
```

### Quality Tuning
```python
# Adjust quality weights
quality_weights = {
    'technical_depth': 0.35,
    'completeness': 0.30,
    'relevance': 0.25,
    'base_score': 0.10
}
```

## Integration with Training

Once data is prepared, it's automatically available for training:

1. Data is saved to `training_data/` directory
2. Validation ensures training readiness
3. Model selection based on data characteristics
4. Automatic hyperparameter optimization
5. Progress tracking via dashboard

## API Reference

See the full API documentation at `/docs/api/training` for detailed endpoint specifications.

## Best Practices

1. **Start Small**: Test with a few URLs first
2. **Monitor Quality**: Review quality scores before training
3. **Domain Matching**: Use appropriate domain configs
4. **Incremental Collection**: Build datasets gradually
5. **Version Control**: Track dataset versions
6. **Regular Validation**: Re-validate before each training

## Support

For issues or questions about the training system, consult:
- Architecture docs: `/docs/architecture/training/`
- API docs: `/docs/api/training`
- Debug logs: Check container logs with `docker logs brain_brain_1`