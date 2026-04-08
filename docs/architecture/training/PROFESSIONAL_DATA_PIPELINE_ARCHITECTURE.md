# Professional Data Preparation & Training Pipeline Architecture

## Overview

A production-grade, enterprise-level system for collecting, processing, and preparing training data for AI models. Designed for technical domains (Drupal, React, Next.js, Rust) and custom knowledge bases.

## Architecture Principles

1. **Modular Design** - Each component is independent and replaceable
2. **Bullet-Proof Validation** - Multiple validation layers at each stage
3. **Comprehensive Logging** - Debug, audit, and performance logging
4. **Error Resilience** - Graceful degradation and retry mechanisms
5. **Quality Assurance** - Automated quality checks and scoring
6. **Scalability** - Handle small datasets to enterprise-scale collections
7. **Observability** - Real-time monitoring, metrics, and tracing

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Data Preparation Pipeline                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: COLLECTION (Robust Multi-Source Scraping)            │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  HTML/Web   │  │ API/JSON    │  │  Docs/MD    │            │
│  │  Collector  │  │  Collector  │  │  Collector  │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│         │                 │                 │                   │
│         └─────────────────┴─────────────────┘                   │
│                           │                                     │
│                  ┌────────▼────────┐                           │
│                  │  Content Buffer  │                           │
│                  │  (Deduplication) │                           │
│                  └────────┬────────┘                           │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 2: VALIDATION (Quality Gates)                           │
├─────────────────────────────────────────────────────────────────┤
│  ✓ Content Quality Score (min 0.7)                             │
│  ✓ Token Count (min thresholds)                                │
│  ✓ Language Detection                                           │
│  ✓ Technical Content Verification                              │
│  ✓ Code Example Validation                                      │
│  ✓ Duplicate Detection                                          │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 3: PREPROCESSING (Domain-Specific Processing)           │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │  Drupal  │  │  React   │  │   Rust   │  │  Custom  │      │
│  │Processor │  │Processor │  │Processor │  │Processor │      │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘      │
│       │              │              │              │           │
│       └──────────────┴──────────────┴──────────────┘           │
│                           │                                     │
│                  ┌────────▼────────┐                           │
│                  │  Normalized     │                           │
│                  │  Content        │                           │
│                  └────────┬────────┘                           │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 4: FORMATTING (Training Data Generation)                │
├─────────────────────────────────────────────────────────────────┤
│  • Conversation Format (system/user/assistant)                 │
│  • Version Context (for version-specific training)             │
│  • Metadata Enrichment                                          │
│  • Token Optimization                                           │
│  • Quality Weighting                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  Phase 5: FINAL VALIDATION (Training Readiness Check)          │
├─────────────────────────────────────────────────────────────────┤
│  ✓ Minimum Examples (domain-specific)                          │
│  ✓ Token Distribution Analysis                                  │
│  ✓ Format Compliance (JSONL)                                    │
│  ✓ Conversation Structure Validation                            │
│  ✓ Training Readiness Score                                     │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│  OUTPUT: Production-Ready Training Data                        │
│  • JSONL Format                                                 │
│  • Quality Metrics Report                                       │
│  • Collection Statistics                                        │
│  • Audit Trail                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Collection Layer

#### Web Collector (Professional Grade)
```python
Features:
- Multiple algorithms (Trafilatura, BeautifulSoup, Readability)
- Intelligent fallback chain
- Rate limiting and politeness
- Robots.txt compliance
- Retry with exponential backoff
- User-agent rotation
- Session management
- Cookie handling
- Redirect following
```

#### Validation on Collection:
- HTTP status validation
- Content-Type verification
- Minimum content length
- HTML structure validation
- Encoding detection and normalization

#### Logging:
```
[COLLECT] 2026-03-26 19:00:01 | URL: drupal.org/docs/develop | Status: 200 | Size: 45KB | Time: 1.2s
[COLLECT] 2026-03-26 19:00:02 | URL: drupal.org/docs/api | Status: 200 | Size: 32KB | Time: 0.8s
[COLLECT] 2026-03-26 19:00:03 | URL: drupal.org/docs/theming | Status: 200 | Size: 28KB | Time: 0.9s
[BUFFER] Deduplicated 2 URLs (content hash match)
[COLLECT] Total: 48 pages | Success: 45 | Failed: 3 | Duplicates: 2
```

### 2. Validation Layer

#### Quality Metrics:
```python
ContentQuality = {
    'technical_depth': 0.0-1.0,  # Code examples, technical terms
    'completeness': 0.0-1.0,      # Has intro, body, examples
    'readability': 0.0-1.0,       # Grammar, structure
    'relevance': 0.0-1.0,         # Domain-specific keywords
    'uniqueness': 0.0-1.0         # Not duplicate
}

Overall Score = weighted_average(ContentQuality)
Threshold: 0.7 (configurable per domain)
```

#### Validation Rules:

**Drupal Domain:**
- Minimum: 50 examples
- Minimum tokens: 5,000
- Required keywords: ['module', 'hook', 'api', 'drupal']
- Code block ratio: >10%

**React Domain:**
- Minimum: 30 examples
- Minimum tokens: 3,000
- Required keywords: ['component', 'jsx', 'react', 'hook']
- Code block ratio: >15%

**Rust Domain:**
- Minimum: 40 examples
- Minimum tokens: 4,000
- Required keywords: ['trait', 'impl', 'cargo', 'rust']
- Code block ratio: >20%

**Custom Knowledge:**
- Minimum: 20 examples
- Minimum tokens: 2,000
- Configurable keywords
- Code block ratio: optional

### 3. Preprocessing Layer

#### Domain-Specific Processors:

**DrupalProcessor:**
- Extract version information from URLs
- Parse hook documentation
- Identify API changes between versions
- Extract code examples
- Link related functions
- Tag with Drupal-specific metadata

**ReactProcessor:**
- Identify component types (functional, class)
- Extract props and state usage
- Parse JSX code blocks
- Identify hooks usage
- Version-specific features (16.8+, 18+)

**RustProcessor:**
- Parse trait definitions
- Extract type signatures
- Identify lifetime annotations
- Parse cargo.toml examples
- Edition-specific features (2018, 2021)

**CustomProcessor:**
- Configurable extraction rules
- Custom regex patterns
- Metadata tagging
- Quality scoring

### 4. Formatting Layer

#### Conversation Format:
```json
{
  "messages": [
    {
      "role": "system",
      "content": "You are an expert in Drupal 11 development..."
    },
    {
      "role": "user",
      "content": "How do I create a custom module?"
    },
    {
      "role": "assistant",
      "content": "To create a custom module in Drupal 11:\n\n1. Create directory...\n\n```php\n// Example code\n```"
    }
  ],
  "metadata": {
    "domain": "drupal",
    "version": "11",
    "quality_score": 0.89,
    "source_url": "https://drupal.org/docs/...",
    "collected_at": "2026-03-26T19:00:00Z",
    "tokens": 450
  }
}
```

### 5. Logging & Debugging

#### Log Levels:
```
DEBUG   - Detailed execution flow, variable values
INFO    - Collection progress, validation results
WARNING - Retries, quality score below threshold
ERROR   - Failed requests, validation failures
CRITICAL- Pipeline failures, data corruption
```

#### Log Structure:
```python
{
    "timestamp": "2026-03-26T19:00:00.123Z",
    "level": "INFO",
    "component": "collector.web",
    "event": "page_collected",
    "data": {
        "url": "https://...",
        "status_code": 200,
        "content_length": 45123,
        "duration_ms": 1234,
        "algorithm": "trafilatura",
        "quality_score": 0.87
    },
    "trace_id": "abc123...",
    "job_id": "job_xyz789"
}
```

#### Debug Files:
```
/app/data/agents/{agent_id}/debug/
├── collection_log.jsonl       # All collection events
├── validation_failures.json   # Failed validations with reasons
├── quality_scores.json        # Quality metrics per page
├── duplicates.json            # Detected duplicates
├── preprocessing_stats.json   # Processor performance
└── final_report.json          # Complete pipeline report
```

### 6. Monitoring & Metrics

#### Real-Time Metrics:
```python
{
    "job_id": "job_abc123",
    "status": "collecting",
    "progress": 0.45,
    "metrics": {
        "pages_total": 100,
        "pages_collected": 45,
        "pages_failed": 3,
        "pages_deduplicated": 2,
        "avg_quality_score": 0.85,
        "avg_page_size_kb": 35,
        "avg_collection_time_ms": 1200,
        "total_tokens": 15234
    },
    "current_phase": "collection",
    "estimated_completion": "2026-03-26T19:05:00Z"
}
```

#### Quality Dashboard:
```
Collection Quality Report
========================
✓ Pages Collected: 95/100 (95% success rate)
✓ Average Quality: 0.87/1.0 (Excellent)
✓ Total Tokens: 45,234
✓ Unique Content: 93/95 (2 duplicates)
✓ Technical Depth: 0.89 (High)
⚠ 3 pages below quality threshold
⚠ 2 pages missing code examples

Validation Results
=================
✓ Minimum examples: 95 (threshold: 50) ✓
✓ Minimum tokens: 45,234 (threshold: 5,000) ✓
✓ Quality score: 0.87 (threshold: 0.70) ✓
✓ Code block ratio: 18% (threshold: 10%) ✓
✓ Technical keywords: Found 34/10 required ✓

STATUS: READY FOR TRAINING
```

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)
- Robust web collector with fallback algorithms
- Content buffer with deduplication
- Base validation framework
- Structured logging system

### Phase 2: Domain Processors (Week 2)
- Drupal processor (priority)
- React processor
- Rust processor
- Custom knowledge processor

### Phase 3: Quality System (Week 3)
- Quality scoring algorithm
- Validation gates
- Debug file generation
- Quality dashboard

### Phase 4: Integration & Testing (Week 4)
- API integration
- UI enhancements
- End-to-end testing
- Performance optimization

## Success Criteria

### Data Quality:
- ✓ 95%+ collection success rate
- ✓ 0.85+ average quality score
- ✓ <1% duplicate content
- ✓ 100% format compliance

### Performance:
- ✓ <2s average page collection time
- ✓ Handle 1000+ pages without failure
- ✓ <5% memory growth over time
- ✓ Real-time progress updates

### Reliability:
- ✓ Automatic retry on transient failures
- ✓ Graceful degradation (fallback algorithms)
- ✓ Complete audit trail
- ✓ Data validation at every stage

### Usability:
- ✓ Clear error messages
- ✓ Progress visibility
- ✓ Quality feedback
- ✓ Debug information available

## Technology Stack

```yaml
Core:
  - Python 3.10+
  - AsyncIO for concurrent collection
  - aiohttp for HTTP requests

Scraping:
  - Trafilatura (primary)
  - BeautifulSoup4 (fallback)
  - Readability (fallback)

Validation:
  - pydantic for data models
  - langdetect for language detection
  - custom quality scoring

Storage:
  - JSONL for training data
  - JSON for metadata/stats
  - SQLite for audit trail (optional)

Monitoring:
  - Prometheus metrics
  - Structured JSON logging
  - Jaeger tracing integration
```

## Configuration

```yaml
# config/data_preparation.yaml

domains:
  drupal:
    min_examples: 50
    min_tokens: 5000
    quality_threshold: 0.75
    required_keywords: ['module', 'hook', 'api', 'drupal']
    code_block_ratio: 0.10
    max_pages: 300
    max_depth: 5

  react:
    min_examples: 30
    min_tokens: 3000
    quality_threshold: 0.75
    required_keywords: ['component', 'jsx', 'react', 'hook']
    code_block_ratio: 0.15
    max_pages: 200
    max_depth: 4

  rust:
    min_examples: 40
    min_tokens: 4000
    quality_threshold: 0.75
    required_keywords: ['trait', 'impl', 'cargo', 'rust']
    code_block_ratio: 0.20
    max_pages: 250
    max_depth: 4

  custom:
    min_examples: 20
    min_tokens: 2000
    quality_threshold: 0.70
    required_keywords: []  # User-defined
    code_block_ratio: 0.0
    max_pages: 150
    max_depth: 3

collection:
  rate_limit: 1.0  # seconds between requests
  timeout: 30  # seconds
  max_retries: 3
  retry_delay: 5  # seconds
  user_agent_rotation: true
  respect_robots_txt: true

logging:
  level: INFO
  format: json
  debug_files: true
  performance_tracking: true
```

---

**Version**: 2.0.0
**Status**: Design Complete - Ready for Implementation
**Priority**: HIGH - Critical for production training system
