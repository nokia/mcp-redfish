# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause


import logging
import re
import socket
import time
import urllib.parse

from common.hosts import update_discovered_hosts

logger = logging.getLogger(__name__)

SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 1900
SSDP_MX = 2
SSDP_ST = "urn:dmtf-org:service:redfish-rest:1"


class SSDPDiscovery:
    """
    SSDPDiscovery discovers Redfish endpoints using SSDP M-SEARCH.
    """

    def __init__(self, timeout: int = 5):
        """
        Args:
            timeout (int): Timeout in seconds for SSDP discovery.
        """
        self.timeout = timeout
        self.found_hosts: list[dict] = []

    def discover(self) -> list[dict]:
        """
        Send SSDP M-SEARCH and collect valid Redfish endpoints from AL header.
        Returns:
            list[dict]: List of discovered hosts with address and service_root.
        """
        message = (
            "M-SEARCH * HTTP/1.1\r\n"
            f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
            'MAN: "ssdp:discover"\r\n'
            f"MX: {SSDP_MX}\r\n"
            f"ST: {SSDP_ST}\r\n\r\n"
        )
        logger.info("Starting SSDP discovery...")
        try:
            with socket.socket(
                socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP
            ) as sock:
                sock.settimeout(self.timeout)
                sock.sendto(message.encode("utf-8"), (SSDP_ADDR, SSDP_PORT))
                start = time.time()
                while time.time() - start < self.timeout:
                    try:
                        data, addr = sock.recvfrom(1024)
                        response = data.decode("utf-8", errors="replace")
                        al_uri = self._parse_al(response)
                        if al_uri and self._is_valid_service_root(al_uri):
                            self.found_hosts.append(
                                {"address": addr[0], "service_root": al_uri}
                            )
                            logger.info(
                                f"Discovered Redfish endpoint: {addr[0]} {al_uri}"
                            )
                        else:
                            logger.debug(
                                f"Received SSDP response from {addr[0]} but no valid AL header found."
                            )
                    except TimeoutError:
                        logger.info("SSDP discovery timed out.")
                        break
                    except Exception as e:
                        logger.error(f"Error receiving SSDP response: {e}")
                        continue
        except Exception as e:
            logger.error(f"Error during SSDP discovery: {e}")
        # Update shared hosts list
        try:
            update_discovered_hosts(self.found_hosts)
        except ImportError:
            logger.warning("update_discovered_hosts not available.")
        return self.found_hosts

    def _is_valid_service_root(self, uri: str) -> bool:
        """
        Validate that the URI is a Redfish service root endpoint.
        Args:
            uri (str): The URI to validate.
        Returns:
            bool: True if valid, False otherwise.
        """
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme != "https":
            logger.debug(f"Service root URI rejected (not https): {uri}")
            return False
        if not parsed.netloc:
            logger.debug(f"Service root URI rejected (missing netloc): {uri}")
            return False
        # Must end with /redfish/v1/ (allow optional trailing slash)
        if not re.match(r"^/redfish/v1/?$", parsed.path):
            logger.debug(f"Service root URI rejected (invalid path): {uri}")
            return False
        return True

    def _parse_al(self, response: str) -> str | None:
        """
        Parse the AL header from an SSDP response.
        Args:
            response (str): The SSDP response string.
        Returns:
            str | None: The AL URI if found, else None.
        """
        # SSDP responses may have multiline headers, so split and search each line
        for line in response.splitlines():
            match = re.match(r"AL:\s*(.*)", line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None


# Example usage:
# discovery = SSDPDiscovery()
# hosts = discovery.discover()
# import pprint; pprint.pprint(hosts)
