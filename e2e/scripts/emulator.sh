#!/bin/bash
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

# Script to manage Redfish Interface Emulator for e2e testing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../certs"
CONFIG_FILE="${SCRIPT_DIR}/../config/emulator-config.json"

# Configuration
EMULATOR_IMAGE="${EMULATOR_IMAGE:-dmtf/redfish-interface-emulator:latest}"
EMULATOR_PORT="${EMULATOR_PORT:-5000}"
EMULATOR_HOST="${EMULATOR_HOST:-127.0.0.1}"
CONTAINER_NAME="${CONTAINER_NAME:-redfish-emulator-e2e}"

# Auto-detect container runtime (Docker or Podman) - can be overridden by environment
CONTAINER_RUNTIME="${CONTAINER_RUNTIME:-}"

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

detect_container_runtime() {
    # Check if CONTAINER_RUNTIME is already set and valid
    if [[ -n "${CONTAINER_RUNTIME}" ]]; then
        case "${CONTAINER_RUNTIME}" in
            docker|podman)
                if command -v "${CONTAINER_RUNTIME}" &> /dev/null && "${CONTAINER_RUNTIME}" info &> /dev/null; then
                    log_info "Using ${CONTAINER_RUNTIME} as container runtime (forced)"
                    return 0
                else
                    log_error "Forced container runtime '${CONTAINER_RUNTIME}' is not available or not running"
                    exit 1
                fi
                ;;
            *)
                log_error "Invalid CONTAINER_RUNTIME value: ${CONTAINER_RUNTIME}. Use 'docker' or 'podman'"
                exit 1
                ;;
        esac
    fi

    # Try Docker first
    if command -v docker &> /dev/null && docker info &> /dev/null; then
        CONTAINER_RUNTIME="docker"
        log_info "Using Docker as container runtime"
        return 0
    fi

    # Try Podman as fallback
    if command -v podman &> /dev/null && podman info &> /dev/null; then
        CONTAINER_RUNTIME="podman"
        log_info "Using Podman as container runtime"
        return 0
    fi

    log_error "Neither Docker nor Podman is available or running"
    log_error "Please install and start either Docker or Podman"
    exit 1
}

check_prerequisites() {
    detect_container_runtime
}

pull_emulator_image() {
    detect_container_runtime
    log_info "Pulling Redfish Interface Emulator image: ${EMULATOR_IMAGE}"
    "${CONTAINER_RUNTIME}" pull "${EMULATOR_IMAGE}"
}

start_emulator() {
    check_prerequisites

    # Check if certificates exist
    if [[ ! -f "${CERT_DIR}/server.crt" || ! -f "${CERT_DIR}/server.key" ]]; then
        log_warn "SSL certificates not found, generating them..."
        "${SCRIPT_DIR}/generate-cert.sh"
    fi

    # Check if container is already running
    if "${CONTAINER_RUNTIME}" ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_warn "Container ${CONTAINER_NAME} is already running"
        return 0
    fi

    # Remove any existing stopped container with the same name
    if "${CONTAINER_RUNTIME}" ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Removing existing container ${CONTAINER_NAME}"
        "${CONTAINER_RUNTIME}" rm "${CONTAINER_NAME}"
    fi

    # Get working directory from the container image
    log_info "Getting working directory from emulator image..."
    WORKDIR=$("${CONTAINER_RUNTIME}" inspect --format='{{.Config.WorkingDir}}' "${EMULATOR_IMAGE}")

    if [[ -z "${WORKDIR}" ]]; then
        log_warn "Could not determine working directory, using /usr/src/app"
        WORKDIR="/usr/src/app"
    fi

    log_info "Starting Redfish Interface Emulator..."
    log_info "  Image: ${EMULATOR_IMAGE}"
    log_info "  Port: ${EMULATOR_HOST}:${EMULATOR_PORT}"
    log_info "  Container: ${CONTAINER_NAME}"
    log_info "  Working Dir: ${WORKDIR}"

    "${CONTAINER_RUNTIME}" run --rm -d \
        --name "${CONTAINER_NAME}" \
        -p "${EMULATOR_HOST}:${EMULATOR_PORT}:5000/tcp" \
        -v "${CONFIG_FILE}:${WORKDIR}/emulator-config.json:ro" \
        -v "${CERT_DIR}/server.crt:${WORKDIR}/server.crt:ro" \
        -v "${CERT_DIR}/server.key:${WORKDIR}/server.key:ro" \
        "${EMULATOR_IMAGE}"

    # Wait for emulator to start
    log_info "Waiting for emulator to start..."
    for i in {1..30}; do
        if curl -k -s "https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1" > /dev/null 2>&1; then
            log_info "✓ Emulator is ready at https://${EMULATOR_HOST}:${EMULATOR_PORT}"
            return 0
        fi
        sleep 1
    done

    log_error "Emulator failed to start within 30 seconds"
    "${CONTAINER_RUNTIME}" logs "${CONTAINER_NAME}" 2>&1 | tail -20
    return 1
}

stop_emulator() {
    detect_container_runtime
    if "${CONTAINER_RUNTIME}" ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Stopping Redfish Interface Emulator..."
        "${CONTAINER_RUNTIME}" stop "${CONTAINER_NAME}"
        log_info "✓ Emulator stopped"
    else
        log_warn "Container ${CONTAINER_NAME} is not running"
    fi
}

status_emulator() {
    detect_container_runtime
    if "${CONTAINER_RUNTIME}" ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        log_info "Redfish Interface Emulator is running"
        echo "Container: ${CONTAINER_NAME}"
        echo "URL: https://${EMULATOR_HOST}:${EMULATOR_PORT}"
        echo "API Root: https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1"
        return 0
    else
        log_warn "Redfish Interface Emulator is not running"
        return 1
    fi
}

test_emulator() {
    if ! status_emulator > /dev/null; then
        log_error "Emulator is not running"
        return 1
    fi

    log_info "Testing emulator connectivity..."

    # Test basic connectivity
    if curl -k -s "https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1" > /dev/null; then
        log_info "✓ Basic connectivity test passed"
    else
        log_error "✗ Basic connectivity test failed"
        return 1
    fi

    # Test API response
    response=$(curl -k -s "https://${EMULATOR_HOST}:${EMULATOR_PORT}/redfish/v1" | jq -r '.Name' 2>/dev/null || echo "")
    if [[ -n "${response}" ]]; then
        log_info "✓ API response test passed (Service: ${response})"
    else
        log_warn "⚠ API response test incomplete (jq may not be available)"
    fi

    log_info "✓ Emulator test completed successfully"
}

logs_emulator() {
    detect_container_runtime
    if "${CONTAINER_RUNTIME}" ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        "${CONTAINER_RUNTIME}" logs "${CONTAINER_NAME}" "$@"
    else
        log_error "Container ${CONTAINER_NAME} is not running"
        return 1
    fi
}

usage() {
    echo "Usage: $0 {start|stop|status|test|logs|pull}"
    echo ""
    echo "Commands:"
    echo "  start   - Start the Redfish Interface Emulator"
    echo "  stop    - Stop the Redfish Interface Emulator"
    echo "  status  - Check if the emulator is running"
    echo "  test    - Test emulator connectivity and API"
    echo "  logs    - Show emulator logs"
    echo "  pull    - Pull the latest emulator image"
    echo ""
    echo "Environment variables:"
    echo "  EMULATOR_IMAGE     - Container image to use (default: ${EMULATOR_IMAGE})"
    echo "  EMULATOR_PORT      - Port to bind to (default: ${EMULATOR_PORT})"
    echo "  EMULATOR_HOST      - Host to bind to (default: ${EMULATOR_HOST})"
    echo "  CONTAINER_RUNTIME  - Force container runtime (docker|podman, default: auto-detect)"
    echo "  CONTAINER_NAME     - Container name (default: ${CONTAINER_NAME})"
}

case "${1:-}" in
    start)
        pull_emulator_image
        start_emulator
        ;;
    stop)
        stop_emulator
        ;;
    status)
        status_emulator
        ;;
    test)
        test_emulator
        ;;
    logs)
        logs_emulator "${@:2}"
        ;;
    pull)
        pull_emulator_image
        ;;
    *)
        usage
        exit 1
        ;;
esac
