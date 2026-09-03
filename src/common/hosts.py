# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause


import logging
import threading
from typing import Any

from . import config as common_config

logger = logging.getLogger(__name__)

_hosts_lock = threading.Lock()
HostEntry = dict[str, Any]

_static_hosts: list[HostEntry] | None = None
_discovered_hosts: list[HostEntry] = []


def _load_static_hosts() -> None:
    """
    Load static hosts from the validated configuration.

    Configuration parsing and defaults have one source of truth. Reading the
    raw environment again here previously made tools see an empty host list
    while ConfigValidator reported the default loopback host.
    """
    global _static_hosts
    _static_hosts = [dict(host) for host in common_config.REDFISH_CFG.get("hosts", [])]


_load_static_hosts()


def update_discovered_hosts(new_hosts: list[HostEntry]) -> None:
    """
    Update the list of discovered hosts in a thread-safe manner.
    Args:
        new_hosts (list[dict]): List of discovered host dictionaries.
    """
    global _discovered_hosts
    with _hosts_lock:
        _discovered_hosts = new_hosts


def get_hosts() -> list[HostEntry]:
    """
    Get the configured Redfish hosts.

    Discovered hosts are intentionally excluded until explicitly added to
    REDFISH_HOSTS by the user.
    Returns:
        list[dict]: List of host dictionaries.
    """
    with _hosts_lock:
        return list(_static_hosts or [])


def get_discovered_hosts() -> list[HostEntry]:
    """
    Get discovered Redfish host candidates.

    These hosts are informational only and are not managed unless explicitly
    added to REDFISH_HOSTS by the user.
    Returns:
        list[dict]: List of discovered host candidate dictionaries.
    """
    with _hosts_lock:
        return list(_discovered_hosts)
