#!/bin/bash
# Quick test script for Professional Collector Integration
# Run this to verify everything works

set -e

echo "=================================="
echo "Professional Collector Quick Test"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 1. Check service health
echo -e "${BLUE}1. Checking Brain API health...${NC}"
HEALTH=$(curl -s http://localhost:8000/health)
if [[ $HEALTH == *"healthy"* ]]; then
    echo -e "${GREEN}✓ API is healthy${NC}"
else
    echo "✗ API is not responding"
    exit 1
fi
echo ""

# 2. Run integration tests
echo -e "${BLUE}2. Running integration tests...${NC}"
docker exec brain-server python /app/test_professional_collector_integration.py > /tmp/test_output.txt 2>&1
if grep -q "All tests passed" /tmp/test_output.txt; then
    echo -e "${GREEN}✓ All integration tests passed${NC}"
    echo "   - Imports: OK"
    echo "   - Domain configs: OK"
    echo "   - API integration: OK"
    echo "   - Professional collector: OK"
else
    echo "✗ Some tests failed"
    cat /tmp/test_output.txt
    exit 1
fi
echo ""

# 3. Test real collection
echo -e "${BLUE}3. Testing real content collection...${NC}"
docker exec brain-server python /tmp/test_with_debug.py > /tmp/collection_test.txt 2>&1
if grep -q "Collected 1 pages" /tmp/collection_test.txt; then
    echo -e "${GREEN}✓ Content collection working${NC}"

    # Extract metrics
    QUALITY=$(grep "Quality:" /tmp/collection_test.txt | awk '{print $3}')
    TIME=$(grep "Time:" /tmp/collection_test.txt | awk '{print $3}')
    TOKENS=$(grep "Total tokens:" /tmp/collection_test.txt | awk '{print $3}')

    echo "   - Quality score: $QUALITY"
    echo "   - Collection time: $TIME"
    echo "   - Tokens extracted: $TOKENS"
else
    echo "✗ Collection test failed"
    cat /tmp/collection_test.txt
    exit 1
fi
echo ""

# 4. Show available agents
echo -e "${BLUE}4. Available agents for testing:${NC}"
docker exec brain-server ls /app/data/agents/ | head -5
echo "   (showing first 5)"
echo ""

# 5. Success summary
echo "=================================="
echo -e "${GREEN}✓ All tests passed!${NC}"
echo "=================================="
echo ""
echo "The Professional Collector is fully operational."
echo ""
echo "Next steps:"
echo "  1. Test with a real agent:"
echo "     ./test_drupal_collection.sh"
echo ""
echo "  2. View logs in real-time:"
echo "     docker logs brain-server -f | grep COLLECT"
echo ""
echo "  3. Check collected data:"
echo "     docker exec brain-server ls -lh /app/data/agents/*/training_data/"
echo ""
echo "See QUICK_START_GUIDE.md for full documentation."
echo ""
