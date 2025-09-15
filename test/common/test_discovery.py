# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Tests for discovery.py module - SSDP Redfish endpoint discovery.

This module tests the SSDP discovery functionality that was previously untested.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Patch sys.path to import from src
sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../src"))
)

from src.common.discovery import SSDPDiscovery


class TestSSDPDiscovery(unittest.TestCase):
    """Test SSDP discovery functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.discovery = SSDPDiscovery(timeout=1)  # Short timeout for tests

    def test_discovery_initialization(self):
        """Test SSDPDiscovery initialization."""
        discovery = SSDPDiscovery(timeout=10)
        self.assertEqual(discovery.timeout, 10)
        self.assertEqual(discovery.found_hosts, [])

    def test_default_timeout(self):
        """Test default timeout value."""
        discovery = SSDPDiscovery()
        self.assertEqual(discovery.timeout, 5)

    def test_valid_service_root_https(self):
        """Test validation of valid HTTPS service root URIs."""
        valid_uris = [
            "https://example.com/redfish/v1/",
            "https://192.168.1.100/redfish/v1",
            "https://server.domain.com:8443/redfish/v1/",
            "https://[::1]/redfish/v1",  # IPv6
        ]

        for uri in valid_uris:
            with self.subTest(uri=uri):
                self.assertTrue(
                    self.discovery._is_valid_service_root(uri),
                    f"URI should be valid: {uri}",
                )

    def test_invalid_service_root_uris(self):
        """Test validation rejects invalid service root URIs."""
        invalid_uris = [
            "http://example.com/redfish/v1/",  # HTTP not HTTPS
            "https://example.com/redfish/v2/",  # Wrong version
            "https://example.com/api/redfish/v1/",  # Wrong path
            "https://example.com/redfish/",  # Incomplete path
            "ftp://example.com/redfish/v1/",  # Wrong protocol
            "not-a-url",  # Not a URL
            "",  # Empty string
            "https:///redfish/v1/",  # Missing netloc
        ]

        for uri in invalid_uris:
            with self.subTest(uri=uri):
                self.assertFalse(
                    self.discovery._is_valid_service_root(uri),
                    f"URI should be invalid: {uri}",
                )

    def test_parse_al_header_valid(self):
        """Test parsing valid AL headers from SSDP responses."""
        valid_responses = [
            "HTTP/1.1 200 OK\r\nAL: https://example.com/redfish/v1/\r\n\r\n",
            "HTTP/1.1 200 OK\r\nal: https://server.domain.com/redfish/v1\r\n\r\n",
            "HTTP/1.1 200 OK\r\nAL:   https://192.168.1.100/redfish/v1/   \r\n\r\n",  # With spaces
            "HTTP/1.1 200 OK\r\nST: urn:dmtf-org:service:redfish-rest:1\r\nAL: https://host/redfish/v1/\r\n\r\n",
        ]

        expected_uris = [
            "https://example.com/redfish/v1/",
            "https://server.domain.com/redfish/v1",
            "https://192.168.1.100/redfish/v1/",
            "https://host/redfish/v1/",
        ]

        for response, expected in zip(valid_responses, expected_uris, strict=False):
            with self.subTest(response=response[:50]):
                result = self.discovery._parse_al(response)
                self.assertEqual(result, expected)

    def test_parse_al_header_invalid(self):
        """Test parsing responses without AL headers."""
        invalid_responses = [
            "HTTP/1.1 200 OK\r\n\r\n",  # No AL header
            "HTTP/1.1 200 OK\r\nST: urn:dmtf-org:service:redfish-rest:1\r\n\r\n",  # No AL
            "HTTP/1.1 404 Not Found\r\n\r\n",  # Wrong status
            "",  # Empty response
            "Not an HTTP response",  # Invalid format
        ]

        for response in invalid_responses:
            with self.subTest(response=response[:30]):
                result = self.discovery._parse_al(response)
                self.assertIsNone(result)

    @patch("socket.socket")
    def test_discovery_socket_error(self, mock_socket):
        """Test handling of socket errors during discovery."""
        # Mock socket to raise an error
        mock_socket.side_effect = OSError("Network error")

        result = self.discovery.discover()

        # Should handle error gracefully and return empty list
        self.assertEqual(result, [])
        self.assertEqual(self.discovery.found_hosts, [])

    @patch("socket.socket")
    def test_discovery_timeout_handling(self, mock_socket):
        """Test handling of socket timeout during discovery."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        # Make recvfrom raise TimeoutError
        mock_sock.recvfrom.side_effect = TimeoutError("Timeout")

        result = self.discovery.discover()

        # Should handle timeout gracefully
        self.assertEqual(result, [])
        self.assertEqual(self.discovery.found_hosts, [])

    @patch("socket.socket")
    def test_discovery_successful_response(self, mock_socket):
        """Test successful discovery with valid response."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        # Mock successful response
        valid_response = (
            "HTTP/1.1 200 OK\r\n"
            "ST: urn:dmtf-org:service:redfish-rest:1\r\n"
            "AL: https://192.168.1.100/redfish/v1/\r\n\r\n"
        )
        mock_sock.recvfrom.side_effect = [
            (valid_response.encode(), ("192.168.1.100", 1900)),
            TimeoutError("Done"),  # End the loop
        ]

        with patch("src.common.discovery.update_discovered_hosts") as mock_update:
            result = self.discovery.discover()

        # Should have found one host
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["address"], "192.168.1.100")
        self.assertEqual(result[0]["service_root"], "https://192.168.1.100/redfish/v1/")

        # Should have called update function
        mock_update.assert_called_once_with(result)

    @patch("socket.socket")
    def test_discovery_invalid_response_filtering(self, mock_socket):
        """Test filtering of invalid responses during discovery."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        responses = [
            # Invalid - HTTP not HTTPS
            (
                "HTTP/1.1 200 OK\r\nAL: http://192.168.1.100/redfish/v1/\r\n\r\n",
                ("192.168.1.100", 1900),
            ),
            # Valid response
            (
                "HTTP/1.1 200 OK\r\nAL: https://192.168.1.101/redfish/v1/\r\n\r\n",
                ("192.168.1.101", 1900),
            ),
            # Invalid - wrong path
            (
                "HTTP/1.1 200 OK\r\nAL: https://192.168.1.102/api/v1/\r\n\r\n",
                ("192.168.1.102", 1900),
            ),
        ]

        # Convert to what recvfrom returns, then add timeout to end
        mock_sock.recvfrom.side_effect = [
            (response[0].encode(), response[1]) for response in responses
        ] + [TimeoutError("Done")]

        with patch("src.common.discovery.update_discovered_hosts"):
            result = self.discovery.discover()

        # Should have found only the valid host
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["address"], "192.168.1.101")

    @patch("socket.socket")
    def test_discovery_no_al_header(self, mock_socket):
        """Test discovery with responses that have no AL header."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        # Response without AL header
        response_no_al = (
            "HTTP/1.1 200 OK\r\nST: urn:dmtf-org:service:redfish-rest:1\r\n\r\n"
        )
        mock_sock.recvfrom.side_effect = [
            (response_no_al.encode(), ("192.168.1.100", 1900)),
            TimeoutError("Done"),
        ]

        result = self.discovery.discover()

        # Should not find any hosts
        self.assertEqual(len(result), 0)

    @patch("socket.socket")
    def test_discovery_malformed_response(self, mock_socket):
        """Test discovery with malformed responses."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        # Malformed response
        malformed_response = b"Not a valid HTTP response"
        mock_sock.recvfrom.side_effect = [
            (malformed_response, ("192.168.1.100", 1900)),
            TimeoutError("Done"),
        ]

        result = self.discovery.discover()

        # Should handle malformed response gracefully
        self.assertEqual(len(result), 0)

    @patch("socket.socket")
    def test_discovery_update_hosts_error(self, mock_socket):
        """Test discovery when update_discovered_hosts fails."""
        mock_sock = MagicMock()
        mock_socket.return_value.__enter__.return_value = mock_sock

        # Valid response
        valid_response = (
            "HTTP/1.1 200 OK\r\nAL: https://192.168.1.100/redfish/v1/\r\n\r\n"
        )
        mock_sock.recvfrom.side_effect = [
            (valid_response.encode(), ("192.168.1.100", 1900)),
            TimeoutError("Done"),
        ]

        # Mock update_discovered_hosts to raise ImportError
        with patch(
            "src.common.discovery.update_discovered_hosts",
            side_effect=ImportError("Not available"),
        ):
            result = self.discovery.discover()

        # Should still return the discovered hosts even if update fails
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["address"], "192.168.1.100")

    def test_discovery_multiple_responses_same_host(self):
        """Test discovery with multiple responses from the same host."""
        with patch("socket.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock

            # Multiple responses from same host
            response = (
                "HTTP/1.1 200 OK\r\nAL: https://192.168.1.100/redfish/v1/\r\n\r\n"
            )
            mock_sock.recvfrom.side_effect = [
                (response.encode(), ("192.168.1.100", 1900)),
                (response.encode(), ("192.168.1.100", 1900)),  # Duplicate
                TimeoutError("Done"),
            ]

            with patch("src.common.discovery.update_discovered_hosts"):
                result = self.discovery.discover()

        # Should have both entries (discovery doesn't deduplicate)
        self.assertEqual(len(result), 2)

    def test_discovery_unicode_handling(self):
        """Test discovery handles unicode characters in responses."""
        with patch("socket.socket") as mock_socket:
            mock_sock = MagicMock()
            mock_socket.return_value.__enter__.return_value = mock_sock

            # Response with unicode characters (should be handled gracefully)
            unicode_response = (
                "HTTP/1.1 200 OK\r\nAL: https://💻.example.com/redfish/v1/\r\n\r\n"
            )
            mock_sock.recvfrom.side_effect = [
                (unicode_response.encode("utf-8"), ("192.168.1.100", 1900)),
                TimeoutError("Done"),
            ]

            with patch("src.common.discovery.update_discovered_hosts"):
                result = self.discovery.discover()

        # Should handle unicode gracefully (though URI might be invalid)
        # Main thing is no exception should be raised
        self.assertIsInstance(result, list)


class TestSSDPDiscoveryConstants(unittest.TestCase):
    """Test SSDP discovery constants and configuration."""

    def test_ssdp_constants(self):
        """Test that SSDP constants are set correctly."""
        from src.common.discovery import SSDP_ADDR, SSDP_MX, SSDP_PORT, SSDP_ST

        self.assertEqual(SSDP_ADDR, "239.255.255.250")
        self.assertEqual(SSDP_PORT, 1900)
        self.assertEqual(SSDP_MX, 2)
        self.assertEqual(SSDP_ST, "urn:dmtf-org:service:redfish-rest:1")


if __name__ == "__main__":
    unittest.main()
