#!/usr/bin/env bash
# Copyright 2026 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

# Copy container tags between two GHCR images (all architectures).
# A repository move does not move GHCR packages, and one registry login
# cannot target two organizations. Pass separate source and dest credentials.
#
# Usage:
#   DST_USERNAME=... DST_TOKEN=... scripts/mirror_ghcr.sh \
#     ghcr.io/nokia/mcp-redfish ghcr.io/nokia-steward/mcp-redfish
#
# Env:
#   SRC_USERNAME, SRC_TOKEN   Optional. Required when the source package is private.
#   DST_USERNAME, DST_TOKEN   Required. Push access to the destination package.
#                             A GitHub App installation token uses the
#                             username x-access-token.
#   TAGS                      Tag names to copy. When unset, every source tag is copied.
#   SKIP_EXISTING=1           Leave destination tags that already exist unchanged.

set -euo pipefail

SRC_IMAGE="${1:-${SRC_IMAGE:-ghcr.io/nokia/mcp-redfish}}"
DST_IMAGE="${2:-${DST_IMAGE:-ghcr.io/nokia-steward/mcp-redfish}}"

if ! command -v skopeo >/dev/null 2>&1; then
  echo "skopeo is required. Install it, then retry." >&2
  exit 1
fi

if [ -z "${DST_USERNAME:-}" ] || [ -z "${DST_TOKEN:-}" ]; then
  echo "Set DST_USERNAME and DST_TOKEN (write access to ${DST_IMAGE})." >&2
  exit 1
fi

src_auth=()
if [ -n "${SRC_TOKEN:-}" ]; then
  if [ -z "${SRC_USERNAME:-}" ]; then
    echo "Set SRC_USERNAME when SRC_TOKEN is set." >&2
    exit 1
  fi
  src_auth=(--src-creds "${SRC_USERNAME}:${SRC_TOKEN}")
fi

if [ -n "${TAGS:-}" ]; then
  # TAGS is a whitespace-separated list of tag names, not full image refs.
  # shellcheck disable=SC2086
  readarray -t tag_array < <(printf '%s\n' ${TAGS})
else
  list_auth=()
  if [ -n "${SRC_TOKEN:-}" ]; then
    list_auth=(--creds "${SRC_USERNAME}:${SRC_TOKEN}")
  fi
  readarray -t tag_array < <(
    skopeo list-tags "${list_auth[@]}" "docker://${SRC_IMAGE}" |
      python3 -c 'import json,sys; print("\n".join(json.load(sys.stdin)["Tags"]))'
  )
fi

if [ "${#tag_array[@]}" -eq 0 ]; then
  echo "No tags to copy from ${SRC_IMAGE}." >&2
  exit 1
fi

copied=0
for tag in "${tag_array[@]}"; do
  if [ -z "${tag}" ]; then
    continue
  fi
  if [ "${SKIP_EXISTING:-0}" = "1" ]; then
    if skopeo inspect --creds "${DST_USERNAME}:${DST_TOKEN}" \
      "docker://${DST_IMAGE}:${tag}" >/dev/null 2>&1; then
      echo "Keeping existing ${DST_IMAGE}:${tag}"
      continue
    fi
  fi
  echo "Copying ${SRC_IMAGE}:${tag} -> ${DST_IMAGE}:${tag}"
  skopeo copy --all \
    "${src_auth[@]}" \
    --dest-creds "${DST_USERNAME}:${DST_TOKEN}" \
    "docker://${SRC_IMAGE}:${tag}" \
    "docker://${DST_IMAGE}:${tag}"
  copied=$((copied + 1))
done

echo "Copied ${copied} tag(s) to ${DST_IMAGE}."
