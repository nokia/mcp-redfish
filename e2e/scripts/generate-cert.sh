#!/bin/bash
# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

# Script to generate self-signed X509 certificates for Redfish Interface Emulator
# This creates certificates that can be used for HTTPS testing

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERT_DIR="${SCRIPT_DIR}/../certs"

# Configuration
CERT_KEY="${CERT_DIR}/server.key"
CERT_CRT="${CERT_DIR}/server.crt"
CERT_DAYS="${CERT_DAYS:-365}"
CERT_SUBJECT="${CERT_SUBJECT:-/C=US/ST=State/L=City/O=Organization/OU=Unit/CN=localhost}"

# Create certificate directory
mkdir -p "${CERT_DIR}"

echo "Generating self-signed X509 certificate for Redfish Interface Emulator..."
echo "Certificate will be valid for ${CERT_DAYS} days"
echo "Subject: ${CERT_SUBJECT}"

# Generate private key
openssl genrsa -out "${CERT_KEY}" 2048

# Generate certificate with SAN for localhost and 127.0.0.1
openssl req -new -x509 -key "${CERT_KEY}" -out "${CERT_CRT}" -days "${CERT_DAYS}" \
    -subj "${CERT_SUBJECT}" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"

# Set appropriate permissions
chmod 600 "${CERT_KEY}"
chmod 644 "${CERT_CRT}"

echo "✓ Certificate generated successfully:"
echo "  Private key: ${CERT_KEY}"
echo "  Certificate: ${CERT_CRT}"

# Display certificate information
echo ""
echo "Certificate information:"
openssl x509 -in "${CERT_CRT}" -text -noout | grep -A 2 "Subject:" || true
openssl x509 -in "${CERT_CRT}" -text -noout | grep -A 3 "Subject Alternative Name:" || true
openssl x509 -in "${CERT_CRT}" -text -noout | grep -A 2 "Validity" || true

echo ""
echo "Certificate fingerprint:"
openssl x509 -in "${CERT_CRT}" -fingerprint -sha256 -noout

echo ""
echo "To trust this certificate locally (Linux), run:"
echo "  sudo cp ${CERT_CRT} /usr/local/share/ca-certificates/redfish-emulator.crt"
echo "  sudo update-ca-certificates"
