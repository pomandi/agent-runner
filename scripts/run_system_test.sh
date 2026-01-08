#!/bin/bash
#
# System Test Runner
# ==================
#
# Runs comprehensive end-to-end system tests
#
# Usage:
#   ./scripts/run_system_test.sh              # Run all tests
#   ./scripts/run_system_test.sh --quick      # Run quick subset
#   ./scripts/run_system_test.sh --verbose    # Verbose output
#

set -e  # Exit on error

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Banner
echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║         AGENT SYSTEM - FULL INTEGRATION TEST SUITE        ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Parse arguments
QUICK_MODE=false
VERBOSE_MODE=false

for arg in "$@"; do
    case $arg in
        --quick)
            QUICK_MODE=true
            ;;
        --verbose|-v)
            VERBOSE_MODE=true
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --quick       Run quick subset of tests"
            echo "  --verbose     Verbose output with print statements"
            echo "  --help        Show this help message"
            echo ""
            exit 0
            ;;
    esac
done

# Check if services are running
echo "📋 Pre-flight checks..."
echo ""

check_service() {
    local service=$1
    local port=$2
    local name=$3

    if nc -z localhost $port 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $name (localhost:$port)"
        return 0
    else
        echo -e "  ${RED}✗${NC} $name (localhost:$port) - NOT RUNNING"
        return 1
    fi
}

all_services_ok=true

if ! check_service qdrant 6333 "Qdrant"; then
    all_services_ok=false
fi

if ! check_service redis 6379 "Redis"; then
    all_services_ok=false
fi

if ! check_service postgresql 5432 "PostgreSQL"; then
    all_services_ok=false
fi

echo ""

if [ "$all_services_ok" = false ]; then
    echo -e "${YELLOW}⚠️  Some services are not running!${NC}"
    echo ""
    echo "Start services with:"
    echo "  docker compose up -d"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Check environment variables
echo "🔑 Checking environment variables..."
echo ""

check_env_var() {
    local var=$1
    local name=$2

    if [ -n "${!var}" ]; then
        echo -e "  ${GREEN}✓${NC} $name set"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC} $name not set"
        return 1
    fi
}

check_env_var "OPENAI_API_KEY" "OPENAI_API_KEY"
check_env_var "ANTHROPIC_API_KEY" "ANTHROPIC_API_KEY"

echo ""

# Build pytest command
PYTEST_CMD="pytest tests/system/test_full_system_integration.py"

if [ "$VERBOSE_MODE" = true ]; then
    PYTEST_CMD="$PYTEST_CMD -v -s"
else
    PYTEST_CMD="$PYTEST_CMD -v"
fi

if [ "$QUICK_MODE" = true ]; then
    echo -e "${YELLOW}ℹ️  Running in QUICK mode (subset of tests)${NC}"
    PYTEST_CMD="$PYTEST_CMD -k 'test_memory_layer_end_to_end or test_invoice_matcher_end_to_end'"
fi

PYTEST_CMD="$PYTEST_CMD --tb=short --color=yes"

echo "🚀 Starting system tests..."
echo ""
echo "Command: $PYTEST_CMD"
echo ""
echo "─────────────────────────────────────────────────────────────"
echo ""

# Run tests
if $PYTEST_CMD; then
    EXIT_CODE=0
    echo ""
    echo "─────────────────────────────────────────────────────────────"
    echo ""
    echo -e "${GREEN}✅ ALL TESTS PASSED!${NC}"
    echo ""
    echo "System Status: HEALTHY ✓"
    echo ""
else
    EXIT_CODE=1
    echo ""
    echo "─────────────────────────────────────────────────────────────"
    echo ""
    echo -e "${RED}❌ SOME TESTS FAILED!${NC}"
    echo ""
    echo "Check the output above for details."
    echo ""
fi

# Summary
echo "📊 Test Summary:"
echo ""
echo "  Components Tested:"
echo "    • Memory Layer (Qdrant + Redis + Embeddings)"
echo "    • Invoice Matcher (LangGraph + Memory)"
echo "    • Feed Publisher (LangGraph + Duplicate Detection)"
echo "    • Monitoring Metrics"
echo "    • Evaluation Framework"
echo "    • Concurrent Operations"
echo "    • System Health"
echo ""

if [ $EXIT_CODE -eq 0 ]; then
    echo "  Result: ${GREEN}✅ PASS${NC}"
else
    echo "  Result: ${RED}❌ FAIL${NC}"
fi

echo ""
echo "For more details, see: tests/TESTING.md"
echo ""

exit $EXIT_CODE
