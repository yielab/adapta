# Brain Platform Scripts

This directory contains all utility scripts for the Brain platform, organized by functionality.

## Quick Start Scripts

### 🚀 Start the Platform
```bash
./scripts/start.sh         # Start local development server
./scripts/start.sh docker   # Start with Docker Compose
./scripts/start.sh prod     # Start in production mode
./scripts/start.sh setup    # Run initial setup only
```

### 🧪 Run Tests
```bash
./scripts/run_tests.sh          # Run all tests
./scripts/run_tests.sh unit     # Run unit tests only
./scripts/run_tests.sh training # Run training system tests
./scripts/run_tests.sh quick    # Run quick smoke tests
```

## Directory Structure

```
scripts/
├── README.md               # This file
├── start.sh               # Main startup script
├── run_tests.sh          # Main test runner
│
├── setup/                 # Setup and installation scripts
│   ├── start.sh          # Original quick start script
│   └── verify_setup.py   # Verify installation
│
├── demo/                  # Demonstration scripts
│   ├── demo_drupal_collection.sh  # Drupal collection demo
│   └── quick_test.sh              # Quick integration test
│
└── testing/              # Test scripts
    ├── training/         # Training system tests
    │   ├── test_collection_direct.py
    │   ├── test_connection_debug.py
    │   ├── test_drupal_collector.py
    │   ├── test_drupal_tokens.py
    │   ├── test_enhanced_scraper.py
    │   ├── test_professional_collector_integration.py
    │   └── test_real_collection.py
    │
    └── integration/      # Integration tests
        ├── test_complete_workflow.sh
        └── test_docker.sh
```

## Script Categories

### Setup Scripts (`setup/`)
- **verify_setup.py**: Verifies Python environment and dependencies
- **start.sh**: Original quick start script (legacy)

### Demo Scripts (`demo/`)
- **demo_drupal_collection.sh**: Demonstrates professional data collection from Drupal.org
- **quick_test.sh**: Quick test to verify professional collector integration

### Testing Scripts (`testing/`)

#### Training Tests (`testing/training/`)
These test the professional data collection and training pipeline:
- **test_professional_collector_integration.py**: Full integration test
- **test_drupal_collector.py**: Test Drupal-specific collector
- **test_enhanced_scraper.py**: Test web scraping with quality validation
- **test_drupal_tokens.py**: Test token counting for Drupal content
- **test_real_collection.py**: Test with real URLs
- **test_collection_direct.py**: Direct collection API test
- **test_connection_debug.py**: Debug connectivity issues

#### Integration Tests (`testing/integration/`)
- **test_complete_workflow.sh**: End-to-end workflow test
- **test_docker.sh**: Docker container and service tests

## Main Scripts

### start.sh
The main startup script with multiple modes:

```bash
# Modes
./scripts/start.sh local      # Local development (default)
./scripts/start.sh docker     # Docker Compose stack
./scripts/start.sh production # Production with gunicorn
./scripts/start.sh setup      # Initial setup only

# Features
- Environment setup and validation
- Python version checking
- Dependency installation
- Model availability checking
- Service health verification
```

### run_tests.sh
Comprehensive test runner:

```bash
# Test types
./scripts/run_tests.sh all         # All test suites
./scripts/run_tests.sh unit        # Unit tests only
./scripts/run_tests.sh integration # Integration tests
./scripts/run_tests.sh training    # Training pipeline tests
./scripts/run_tests.sh docker      # Docker tests
./scripts/run_tests.sh quick       # Quick smoke tests

# Options
./scripts/run_tests.sh all verbose # Show detailed output
```

## Usage Examples

### First Time Setup
```bash
# 1. Run initial setup
./scripts/start.sh setup

# 2. Download models (follow instructions)
pip install huggingface-hub
huggingface-cli download ...

# 3. Start the platform
./scripts/start.sh
```

### Development Workflow
```bash
# Start services
./scripts/start.sh docker

# Run tests
./scripts/run_tests.sh quick

# Test training pipeline
./scripts/demo/demo_drupal_collection.sh

# Run full test suite
./scripts/run_tests.sh all
```

### Production Deployment
```bash
# Start in production mode
./scripts/start.sh production

# Or with Docker
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

## Environment Variables

Scripts respect these environment variables:
- `BRAIN_ENV`: Environment (development/production)
- `LOG_LEVEL`: Logging level (DEBUG/INFO/WARNING/ERROR)
- `API_HOST`: API host (default: 0.0.0.0)
- `API_PORT`: API port (default: 8000)

## Troubleshooting

### Scripts not executable
```bash
chmod +x scripts/*.sh
chmod +x scripts/**/*.sh
```

### Python dependencies missing
```bash
./scripts/start.sh setup
```

### Models not found
Follow instructions in `docs/guides/MODELS_DOWNLOAD_GUIDE.md`

### Services not starting
```bash
# Check logs
docker-compose logs -f

# Restart services
docker-compose restart

# Clean restart
docker-compose down && docker-compose up -d
```

## Contributing

When adding new scripts:
1. Place in appropriate subdirectory
2. Make executable: `chmod +x script.sh`
3. Add documentation to this README
4. Include usage instructions in script
5. Use consistent color coding and output format