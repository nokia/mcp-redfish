# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause


import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

_hosts_lock = threading.Lock()
_static_hosts = None
_discovered_hosts = []


def _load_static_hosts() -> None:
    """
    Load static hosts from the REDFISH_HOSTS environment variable.
    """
    global _static_hosts
    hosts_env = os.environ.get("REDFISH_HOSTS", "[]")
    try:
        _static_hosts = json.loads(hosts_env)
    except Exception as e:
        logger.error(f"Failed to parse REDFISH_HOSTS: {e}")
        _static_hosts = []


_load_static_hosts()


def update_discovered_hosts(new_hosts: list[dict]) -> None:
    """
    Update the list of discovered hosts in a thread-safe manner.
    Args:
        new_hosts (list[dict]): List of discovered host dictionaries.
    """
    global _discovered_hosts
    with _hosts_lock:
        _discovered_hosts = new_hosts


def get_hosts() -> list[dict]:
    """
    Get the merged list of static and discovered hosts, avoiding duplicates by address.
    Returns:
        list[dict]: List of host dictionaries.
    """
    with _hosts_lock:
        # Static hosts take precedence over discovered hosts
        all_hosts = {h["address"]: h for h in (_static_hosts or [])}
        for h in _discovered_hosts:
            if h["address"] not in all_hosts:
                all_hosts[h["address"]] = h
        return list(all_hosts.values())
