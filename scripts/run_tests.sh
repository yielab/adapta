#!/bin/bash
# Main test runner script for Brain platform

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🧠 Brain Platform - Test Runner"
echo "================================"
echo ""

# Parse arguments
TEST_TYPE=${1:-all}
VERBOSE=${2:-false}

show_usage() {
    echo "Usage: $0 [test_type] [verbose]"
    echo ""
    echo "Test types:"
    echo "  all        - Run all tests (default)"
    echo "  unit       - Run unit tests only"
    echo "  integration- Run integration tests"
    echo "  training   - Run training system tests"
    echo "  docker     - Run Docker container tests"
    echo "  quick      - Run quick smoke tests"
    echo ""
    echo "Options:"
    echo "  verbose    - Show detailed output"
    echo ""
    echo "Examples:"
    echo "  $0              # Run all tests"
    echo "  $0 unit         # Run unit tests only"
    echo "  $0 training     # Run training tests"
    echo "  $0 all verbose  # Run all tests with verbose output"
}

run_unit_tests() {
    echo -e "${BLUE}Running unit tests...${NC}"
    python -m pytest tests/ -v --ignore=tests/integration
    echo -e "${GREEN}✓ Unit tests passed${NC}"
}

run_integration_tests() {
    echo -e "${BLUE}Running integration tests...${NC}"

    # Check if services are running
    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Services not running. Starting them...${NC}"
        docker-compose up -d
        sleep 5
    fi

    # Run integration tests
    python -m pytest tests/integration -v

    # Run workflow tests
    ./scripts/testing/integration/test_complete_workflow.sh

    echo -e "${GREEN}✓ Integration tests passed${NC}"
}

run_training_tests() {
    echo -e "${BLUE}Running training system tests...${NC}"

    # Check if service is running
    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "${RED}✗ Services not running. Please start them first.${NC}"
        exit 1
    fi

    # Run each training test
    for test in scripts/testing/training/test_*.py; do
        echo "  Running $(basename $test)..."
        if [ "$VERBOSE" = "verbose" ]; then
            python "$test"
        else
            python "$test" > /tmp/test_output.log 2>&1
            if [ $? -eq 0 ]; then
                echo -e "    ${GREEN}✓ Passed${NC}"
            else
                echo -e "    ${RED}✗ Failed${NC}"
                echo "    Check /tmp/test_output.log for details"
                exit 1
            fi
        fi
    done

    echo -e "${GREEN}✓ Training tests passed${NC}"
}

run_docker_tests() {
    echo -e "${BLUE}Running Docker tests...${NC}"
    ./scripts/testing/integration/test_docker.sh
    echo -e "${GREEN}✓ Docker tests passed${NC}"
}

run_quick_tests() {
    echo -e "${BLUE}Running quick smoke tests...${NC}"

    # Health check
    echo "  Checking API health..."
    if curl -s http://localhost:8000/health | grep -q "healthy"; then
        echo -e "    ${GREEN}✓ API is healthy${NC}"
    else
        echo -e "    ${RED}✗ API health check failed${NC}"
        exit 1
    fi

    # Basic functionality
    echo "  Testing basic chat completion..."
    response=$(curl -s -X POST http://localhost:8000/v1/chat/completions \
        -H "Content-Type: application/json" \
        -d '{"model":"qwen2.5-3b-instruct","messages":[{"role":"user","content":"Hi"}]}' | grep -c "content")

    if [ "$response" -gt 0 ]; then
        echo -e "    ${GREEN}✓ Chat completion works${NC}"
    else
        echo -e "    ${RED}✗ Chat completion failed${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Quick tests passed${NC}"
}

# Main execution
case "$TEST_TYPE" in
    all)
        run_unit_tests
        echo ""
        run_integration_tests
        echo ""
        run_training_tests
        echo ""
        run_docker_tests
        ;;
    unit)
        run_unit_tests
        ;;
    integration)
        run_integration_tests
        ;;
    training)
        run_training_tests
        ;;
    docker)
        run_docker_tests
        ;;
    quick)
        run_quick_tests
        ;;
    help|--help|-h)
        show_usage
        exit 0
        ;;
    *)
        echo -e "${RED}Unknown test type: $TEST_TYPE${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}🎉 All tests completed successfully!${NC}"