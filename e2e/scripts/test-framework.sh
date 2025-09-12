#!/bin/bash
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

# Modern Python-based e2e test using the extensible test framework

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$(dirname "${SCRIPT_DIR}")")"

# Configuration
EMULATOR_HOST="${EMULATOR_HOST:-127.0.0.1}"
EMULATOR_PORT="${EMULATOR_PORT:-5000}"
TEST_TIMEOUT="${TEST_TIMEOUT:-60}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."

    # Check if emulator is running
    if ! "${SCRIPT_DIR}/emulator.sh" status > /dev/null; then
        log_error "Redfish Interface Emulator is not running"
        log_info "Run 'make e2e-start' to start the emulator"
        exit 1
    fi

    # Check if emulator is reachable
    if ! curl -k -s "https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1" > /dev/null; then
        log_error "Cannot reach emulator at https://${EMULATOR_HOST}:${EMULATOR_PORT}"
        exit 1
    fi

    # Check if Node.js is available for MCP Inspector
    if ! command -v npx &> /dev/null; then
        log_error "Node.js/npx not found - MCP Inspector CLI not available"
        log_info "Install Node.js to run e2e tests"
        exit 1
    fi

    log_info "✓ Prerequisites check passed"
}

# Test emulator API directly to ensure it's working
test_emulator_api() {
    log_info "Testing emulator API directly..."

    # Test service root
    local service_root
    service_root=$(curl -k -s "https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1" | jq -r '.Name' 2>/dev/null || echo "")

    if [[ -n "${service_root}" ]]; then
        log_info "✓ Service root accessible (Service: ${service_root})"
    else
        log_warn "⚠ Service root test incomplete (response received but jq may not be available)"
    fi

    # Test systems endpoint
    if curl -k -s "https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1/Systems" > /dev/null; then
        log_info "✓ Systems endpoint accessible"
    else
        log_error "✗ Systems endpoint not accessible"
        return 1
    fi

    log_info "✓ Emulator API test passed"
}

# Run Python-based e2e tests
run_python_tests() {
    log_info "Running Python-based e2e test framework..."

    cd "${PROJECT_DIR}"

    # Set environment variables
    export EMULATOR_HOST="${EMULATOR_HOST}"
    export EMULATOR_PORT="${EMULATOR_PORT}"

    # Run the Python test framework
    if timeout "${TEST_TIMEOUT}s" bash -c "cd '${PROJECT_DIR}' && uv run python e2e/python/test_runner.py"; then
        log_info "✓ Python e2e test framework completed successfully"
        return 0
    else
        local exit_code=$?
        if [ $exit_code -eq 124 ]; then
            log_error "✗ Python e2e tests timed out after ${TEST_TIMEOUT}s"
        else
            log_error "✗ Python e2e tests failed with exit code: $exit_code"
        fi
        return 1
    fi
}

# Main test execution
main() {
    log_info "Starting modern Python-based e2e tests..."
    log_info "Emulator: https://${EMULATOR_HOST}:${EMULATOR_PORT}"
    log_info "Timeout: ${TEST_TIMEOUT}s"
    echo

    check_prerequisites
    test_emulator_api
    run_python_tests

    echo
    log_info "✅ All e2e tests completed successfully!"
}

# Cleanup function
cleanup() {
    # Kill any background processes
    jobs -p | xargs -r kill 2>/dev/null || true
}

# Set trap for cleanup
trap cleanup EXIT

# Run main function
main "$@"
