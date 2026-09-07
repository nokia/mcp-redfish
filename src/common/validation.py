# Copyright 2025 Nokia
# Licensed under the BSD 3-Clause License.
# SPDX-License-Identifier: BSD-3-Clause

"""
Configuration validation module for MCP Redfish server.
Provides schema validation and error handling for environment variables.
"""

import ipaddress
import json
import logging
import os
import stat
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlparse

from fastmcp.settings import Settings as FastMCPSettings
from redfish.rest.v1 import AuthMethod

from .logging_utils import redact_sensitive_text

logger = logging.getLogger(__name__)

# Repeated verbatim in README, CHANGELOG, AGENTS.md and docs/MCP_AUTH.md.
MCP_AUTH_BREAKING_CHANGE_HINT = (
    "Breaking change: HTTP MCP transports (sse, streamable-http) now require "
    "authentication. Set MCP_AUTH_MODE (and the matching MCP_AUTH_* variables), "
    "or set MCP_HTTP_AUTH=false to keep unauthenticated HTTP. stdio is unchanged. "
    "See docs/MCP_AUTH.md."
)

# Official MCP transport types as defined in FastMCP
MCPTransportType = Literal["stdio", "streamable-http", "sse"]
VALID_MCP_TRANSPORTS = ["stdio", "streamable-http", "sse"]

MCPAuthMode = Literal[
    "none", "token", "remote_oauth", "oauth_proxy", "oidc_proxy", "static_token"
]
VALID_MCP_AUTH_MODES = [
    "none",
    "token",
    "remote_oauth",
    "oauth_proxy",
    "oidc_proxy",
    "static_token",
]
IMPLEMENTED_MCP_AUTH_MODES = (
    "none",
    "token",
    "remote_oauth",
    "oauth_proxy",
    "oidc_proxy",
)
STDIO_MCP_TRANSPORT = "stdio"
HTTP_MCP_TRANSPORTS = ("streamable-http", "sse")
DEFAULT_BIND_HOST = "127.0.0.1"
DEFAULT_BIND_PORT = 8000
HMAC_MIN_SECRET_LENGTH = 32
JWT_SIGNING_KEY_MIN_LENGTH = 32
DEFAULT_ALLOWED_CLIENT_REDIRECT_URIS = [
    "http://localhost:*",
    "http://127.0.0.1:*",
]
UNSAFE_REDIRECT_URI_SCHEMES = ("javascript:", "data:", "file:", "vbscript:")
VALID_STORAGE_BACKENDS = ("disk", "redis")


@dataclass
class HostConfig:
    """Configuration for a single Redfish host."""

    address: str
    port: int | None = None
    username: str | None = None
    password: str | None = None
    auth_method: str | None = None
    tls_server_ca_cert: str | None = None
    tls_verify: bool | None = None

    def __post_init__(self) -> None:
        """Validate host configuration after initialization."""
        if not self.address:
            raise ValueError("Host address cannot be empty")

        if self.port is not None and (self.port < 1 or self.port > 65535):
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")

        if self.auth_method and self.auth_method not in (
            AuthMethod.BASIC,
            AuthMethod.SESSION,
        ):
            raise ValueError(
                f"Invalid auth_method: {self.auth_method}. Must be one of: {AuthMethod.BASIC}, {AuthMethod.SESSION}"
            )

        if self.tls_verify is not None and not isinstance(self.tls_verify, bool):
            raise ValueError("tls_verify must be a boolean")


@dataclass
class RedfishConfig:
    """Complete Redfish configuration."""

    hosts: list[HostConfig] = field(default_factory=list)
    port: int = 443
    auth_method: str = AuthMethod.SESSION
    username: str = ""
    password: str = ""
    tls_server_ca_cert: str | None = None
    tls_verify: bool = True
    discovery_enabled: bool = False
    discovery_interval: int = 30

    def __post_init__(self) -> None:
        """Validate Redfish configuration after initialization."""
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got: {self.port}")

        if self.auth_method not in (AuthMethod.BASIC, AuthMethod.SESSION):
            raise ValueError(
                f"Invalid auth_method: {self.auth_method}. Must be one of: {AuthMethod.BASIC}, {AuthMethod.SESSION}"
            )

        if not isinstance(self.tls_verify, bool):
            raise ValueError("tls_verify must be a boolean")

        if self.discovery_interval < 1:
            raise ValueError(
                f"Discovery interval must be positive, got: {self.discovery_interval}"
            )

        if not self.hosts:
            logger.warning("No Redfish hosts configured")


class ConfigurationError(Exception):
    """Raised when configuration validation fails."""

    pass


class AuthConfigurationError(ConfigurationError):
    """Raised when MCP HTTP authentication configuration is invalid.

    Auth misconfiguration must abort the process and must not use the
    legacy REDFISH configuration fallback.
    """

    pass


class HttpAuthRequiredError(AuthConfigurationError):
    """Raised when an HTTP transport is started with no MCP authentication.

    Kept distinct from other auth misconfiguration so the breaking-change
    migration message reaches the operators whose working deployment just
    stopped starting, and not the ones who configured auth and then made an
    unrelated mistake.
    """

    pass


@dataclass
class MCPAuthConfig:
    """MCP HTTP authentication and listen-socket TLS configuration."""

    mode: MCPAuthMode = "none"
    http_auth: bool = True
    allow_remote_sse: bool = False
    tls_terminated: bool = False
    tls_certfile: str | None = None
    tls_keyfile: str | None = None
    token_type: Literal["jwt", "introspection"] = "jwt"
    token_leeway_seconds: int = 60
    required_scopes: list[str] | None = None
    base_url: str | None = None
    jwt_jwks_uri: str | None = None
    jwt_issuer: str | None = None
    jwt_audience: str | None = None
    jwt_algorithm: str | None = None
    jwt_public_key: str | None = field(default=None, repr=False)
    introspection_url: str | None = None
    introspection_client_id: str | None = None
    introspection_client_secret: str | None = field(default=None, repr=False)
    introspection_auth_method: Literal["client_secret_basic", "client_secret_post"] = (
        "client_secret_basic"
    )
    introspection_issuer: str | None = None
    introspection_audience: str | None = None
    introspection_allowed_token_types: list[str] = field(
        default_factory=lambda: ["bearer", "access_token"]
    )
    introspection_allow_private: bool = False
    jwks_allow_private: bool = False
    authorization_servers: list[str] | None = None
    upstream_authorization_endpoint: str | None = None
    upstream_token_endpoint: str | None = None
    oidc_config_url: str | None = None
    oidc_audience: str | None = None
    client_id: str | None = None
    client_secret: str | None = field(default=None, repr=False)
    jwt_signing_key: str | None = field(default=None, repr=False)
    storage_encryption_key: str | None = field(default=None, repr=False)
    allowed_client_redirect_uris: list[str] | None = None
    require_consent: str = "true"
    forward_pkce: bool = True
    redirect_path: str = "/auth/callback"
    oidc_verify_id_token: bool = False
    storage_backend: Literal["disk", "redis"] = "disk"
    redis_url: str | None = field(default=None, repr=False)

    def is_real_mode(self) -> bool:
        """Return True when a FastMCP verifier/provider mode is selected."""
        return self.mode not in ("none",)

    def is_proxy_mode(self) -> bool:
        """Return True when FastMCP mints tokens and stores upstream credentials."""
        return self.mode in ("oauth_proxy", "oidc_proxy")

    def has_in_process_tls(self) -> bool:
        """Return True when both server cert and key paths are configured."""
        return bool(self.tls_certfile and self.tls_keyfile)

    def uses_ssrf_protected_fetch(self) -> bool:
        """Return whether this configuration performs an SSRF-checked fetch."""
        jwks_fetch = (bool(self.jwt_jwks_uri) or self.mode == "oidc_proxy") and (
            not self.jwks_allow_private
        )
        introspection_fetch = (
            self.token_type == "introspection"  # nosec B105
            and not self.introspection_allow_private
        )
        return bool(jwks_fetch or introspection_fetch)

    def consent_for_fastmcp(self) -> bool | Literal["remember", "external"]:
        """Map MCP_AUTH_REQUIRE_CONSENT to FastMCP's constructor value."""
        if self.require_consent == "true":
            return True
        if self.require_consent == "false":
            return False
        if self.require_consent == "remember":
            return "remember"
        if self.require_consent == "external":
            return "external"
        raise AuthConfigurationError(
            "MCP_AUTH_REQUIRE_CONSENT must be true, false, remember, or external"
        )


@dataclass
class MCPConfig:
    """MCP server configuration."""

    transport: MCPTransportType = "stdio"
    log_level: str = "INFO"
    auth: MCPAuthConfig | None = None

    def __post_init__(self) -> None:
        """Validate MCP configuration after initialization."""
        if self.transport not in VALID_MCP_TRANSPORTS:
            raise ValueError(
                f"Invalid transport: {self.transport}. Must be one of: {VALID_MCP_TRANSPORTS}"
            )

        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(
                f"Invalid log_level: {self.log_level}. Must be one of: {valid_log_levels}"
            )

        self.log_level = self.log_level.upper()


def effective_bind_host() -> str:
    """Return the HTTP bind address this project will pass to mcp.run().

    Unset or empty FASTMCP_HOST binds 127.0.0.1. Detection uses the environment
    (and .env load), not mcp.settings.host.
    """
    host = os.getenv("FASTMCP_HOST")
    if host is None or host.strip() == "":
        return DEFAULT_BIND_HOST
    return normalize_bind_host(host)


def normalize_bind_host(host: str) -> str:
    """Normalize a bind address without accepting hostnames as loopback.

    Uvicorn expects an IPv6 literal without URL brackets. Accepting ``[::1]``
    here avoids both a false non-loopback classification and an invalid bind
    value when an operator copies the address from a URL.
    """
    normalized = host.strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        return normalized[1:-1]
    return normalized


def effective_bind_port() -> int:
    """Return the HTTP bind port this project will pass to mcp.run()."""
    raw = os.getenv("FASTMCP_PORT")
    if raw is None or raw.strip() == "":
        return DEFAULT_BIND_PORT
    try:
        port = int(raw)
    except ValueError as e:
        raise AuthConfigurationError("FASTMCP_PORT must be an integer") from e
    if port < 1 or port > 65535:
        raise AuthConfigurationError(
            f"FASTMCP_PORT must be between 1 and 65535, got: {port}"
        )
    return port


def is_http_transport(transport: str) -> bool:
    """Return True for every transport that opens a network listener.

    Defined as "not stdio" rather than as an allowlist of known HTTP
    transports so that a transport this module does not recognise inherits the
    HTTP fail-closed rules instead of skipping them. Callers that start the
    server must use this same predicate to choose the HTTP code path.
    """
    return transport != STDIO_MCP_TRANSPORT


def is_loopback_bind(host: str) -> bool:
    """Return True if host is a loopback IP for the TLS-assertion rule.

    Treats 127.0.0.1, ::1, and IPv4-mapped ::ffff:127.0.0.1 as loopback.
    Does not treat the hostname localhost as loopback.
    """
    try:
        return ipaddress.ip_address(normalize_bind_host(host)).is_loopback
    except ValueError:
        return False


def listen_scheme(auth_config: MCPAuthConfig) -> str:
    """Return http or https from in-process TLS config, not FastMCP's banner."""
    return "https" if auth_config.has_in_process_tls() else "http"


def host_origin_protection_for_run(
    bind_host: str | None = None,
) -> bool | Literal["auto"]:
    """Host/Origin protection passed to mcp.run() for HTTP transports.

    Loopback defaults to FastMCP's ``auto`` behavior. Non-loopback defaults to
    strict protection so the Kubernetes/remote bind does not silently disable
    Host and Origin validation.
    """
    raw = os.getenv("FASTMCP_HTTP_HOST_ORIGIN_PROTECTION")
    if raw is None or raw.strip() == "":
        host = normalize_bind_host(bind_host or effective_bind_host())
        return "auto" if is_loopback_bind(host) else True
    normalized = raw.strip().lower()
    if normalized == "auto":
        return "auto"
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    raise AuthConfigurationError(
        "FASTMCP_HTTP_HOST_ORIGIN_PROTECTION must be true, false, or auto"
    )


def _get_auth_bool(key: str, default: bool) -> bool:
    """Boolean env helper that always raises AuthConfigurationError."""
    value = os.getenv(key)
    if value is None or value.strip() == "":
        return default
    normalized = value.strip().lower()
    if normalized in ("true", "1", "yes", "on"):
        return True
    if normalized in ("false", "0", "no", "off"):
        return False
    raise AuthConfigurationError(f"Environment variable {key} must be a boolean value")


def _get_auth_int(key: str, default: int, *, minimum: int = 0) -> int:
    """Integer env helper for authentication policy values."""
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as e:
        raise AuthConfigurationError(f"{key} must be an integer") from e
    if value < minimum:
        raise AuthConfigurationError(f"{key} must be at least {minimum}")
    return value


def _reject_fastmcp_server_auth_env() -> None:
    for key in os.environ:
        if key == "FASTMCP_SERVER_AUTH" or key.startswith("FASTMCP_SERVER_AUTH_"):
            raise AuthConfigurationError(
                "FASTMCP_SERVER_AUTH is not supported. Configure MCP authentication "
                "with MCP_AUTH_* variables; dual wiring with FastMCP's "
                "FASTMCP_SERVER_AUTH is unsupported."
            )


def effective_fastmcp_settings() -> FastMCPSettings:
    """Read the FastMCP settings that will actually apply to this MCP Server.

    FastMCP resolves its own FASTMCP_* variables and, unless FASTMCP_ENV_FILE
    says otherwise, a .env file. Settings this project does not pass explicitly
    to mcp.run() still take effect, so checks below must look at the effective
    value rather than at os.environ alone.
    """
    try:
        return FastMCPSettings()
    except Exception as e:
        raise AuthConfigurationError(f"Invalid FASTMCP_* setting: {e}") from e


def configured_proxy_env_var() -> str | None:
    """Name of the proxy variable FastMCP will route proxy-mode fetches through.

    Mirrors the order in fastmcp.server.auth.ssrf._configured_proxy_url. Returns
    the variable name rather than the value, which routinely embeds credentials.
    """
    for name in ("HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy"):
        if os.getenv(name):
            return name
    return None


def _validate_ssrf_trust_proxy(auth: MCPAuthConfig) -> None:
    """Permit proxy-delegated IdP egress, but not the way that fails silently.

    Verifiers are built with ssrf_safe=True, so by default FastMCP resolves the
    JWKS host itself, refuses private, loopback, and link-local addresses, and
    pins the connection to a validated IP. That still works behind an enterprise
    proxy — httpx keeps trust_env=True, so HTTPS_PROXY is honoured — as long as
    this host can resolve the IdP name to a public address.

    Where it does not work is the locked-down case: no external DNS, or a proxy
    that refuses CONNECT to a bare IP literal. FASTMCP_SSRF_TRUST_PROXY exists
    for exactly that, handing the hostname URL to the proxy so the proxy owns
    DNS and egress, and it is a legitimate production configuration.

    The one arrangement worth refusing is enabling it with no proxy set. FastMCP
    then rejects the fetch rather than going direct unprotected, but only at the
    first token verification, which surfaces as every request failing to
    authenticate long after startup reported success.
    """
    if not auth.uses_ssrf_protected_fetch():
        return
    if not effective_fastmcp_settings().ssrf_trust_proxy:
        return
    if configured_proxy_env_var() is None:
        raise AuthConfigurationError(
            "FASTMCP_SSRF_TRUST_PROXY is enabled but neither HTTPS_PROXY nor "
            "ALL_PROXY is set. FastMCP would refuse every JWKS and OAuth "
            "metadata fetch at the first token verification. Set the proxy, or "
            "unset FASTMCP_SSRF_TRUST_PROXY to use DNS and address validation."
        )


def _reject_wildcard_host_origin_allowlists() -> None:
    """Refuse "*" in the Host/Origin allowlists FastMCP applies on HTTP.

    These two are not passed to mcp.run(): an explicit list would also suppress
    FastMCP's "auto" behaviour of trusting the loopback bind address. They are
    validated here instead so a wildcard cannot silently disable the
    DNS-rebinding guard.
    """
    settings = effective_fastmcp_settings()
    for name, values in (
        ("FASTMCP_HTTP_ALLOWED_HOSTS", settings.http_allowed_hosts),
        ("FASTMCP_HTTP_ALLOWED_ORIGINS", settings.http_allowed_origins),
    ):
        for value in values or ():
            normalized = value.strip()
            if not normalized or any(char in normalized for char in ("*", "?", "[")):
                raise AuthConfigurationError(
                    f'{name} must not contain "{value}". Empty values and pattern '
                    "metacharacters disable or over-broaden the "
                    "Host/Origin guard that protects HTTP transports against "
                    "DNS rebinding. List the exact hosts or origins instead."
                )


def _validate_host_origin_policy(bind_host: str) -> None:
    """Require an effective Host allowlist for strict remote HTTP binds."""
    protection = host_origin_protection_for_run(bind_host)
    if is_loopback_bind(bind_host) or protection is False:
        return
    settings = effective_fastmcp_settings()
    if not settings.http_allowed_hosts:
        raise AuthConfigurationError(
            "Non-loopback HTTP binds require explicit "
            "FASTMCP_HTTP_ALLOWED_HOSTS when Host/Origin protection is enabled. "
            "List the exact Service, Ingress, or public hostnames clients use."
        )


def _parse_json_string_list(key: str) -> list[str] | None:
    raw = os.getenv(key)
    if raw is None or raw.strip() == "":
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise AuthConfigurationError(
            f"{key} must be a JSON array of strings: {e}"
        ) from e
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise AuthConfigurationError(f"{key} must be a JSON array of strings")
    return value


def _require_https_url(
    value: str,
    name: str,
    *,
    allow_loopback_http: bool = False,
) -> None:
    parsed = urlparse(value)
    if parsed.scheme in ("javascript", "data") or not parsed.scheme:
        raise AuthConfigurationError(f"{name} must be an absolute http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise AuthConfigurationError(f"{name} must not contain userinfo")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise AuthConfigurationError(f"{name} must be an absolute http(s) URL")
    if parsed.scheme == "https":
        return
    if not allow_loopback_http:
        raise AuthConfigurationError(f"{name} must be an HTTPS URL")
    hostname = parsed.hostname
    if hostname not in ("127.0.0.1", "::1"):
        raise AuthConfigurationError(
            f"{name} may use http:// only for loopback (127.0.0.1 or ::1)"
        )


def _validate_tls_file_pair(certfile: str | None, keyfile: str | None) -> None:
    if not certfile and not keyfile:
        return
    if not certfile or not keyfile:
        raise AuthConfigurationError(
            "MCP_TLS_CERTFILE and MCP_TLS_KEYFILE must both be set, or both unset"
        )
    for name, path in (
        ("MCP_TLS_CERTFILE", certfile),
        ("MCP_TLS_KEYFILE", keyfile),
    ):
        if not os.path.isfile(path):
            raise AuthConfigurationError(f"{name} path does not exist: {path}")
        if not os.access(path, os.R_OK):
            raise AuthConfigurationError(f"{name} path is not readable: {path}")


def warn_if_world_readable_key(keyfile: str) -> None:
    """Warn if the TLS private key is world-readable. Do not refuse."""
    try:
        mode = os.stat(keyfile).st_mode
    except OSError:
        return
    if mode & stat.S_IROTH:
        logger.warning(
            "MCP_TLS_KEYFILE is world-readable. Restrict permissions if this "
            "file is not a deliberately shared secret mount."
        )


def _reject_jwt_algorithm_none(algorithm: str | None) -> None:
    """Refuse the JWT ``none`` algorithm in every mode that can pass it through."""
    if algorithm is not None and algorithm.strip().lower() == "none":
        raise AuthConfigurationError("MCP_AUTH_JWT_ALGORITHM none is not allowed")


def _redirect_pattern_host(pattern: str) -> str:
    """Return the host part of a FastMCP redirect pattern.

    Port wildcards such as ``http://localhost:*`` keep a real hostname.
    Unrestricted hosts (``*``, ``https://*``) collapse to ``*``.
    """
    rest = pattern.split("://", 1)[-1]
    hostport = rest.split("/", 1)[0]
    if hostport.startswith("["):
        end = hostport.find("]")
        if end != -1:
            return hostport[1:end]
    if hostport.count(":") == 1:
        return hostport.rsplit(":", 1)[0]
    return hostport


def _validate_jwt_fields(auth: MCPAuthConfig, *, require_issuer_audience: bool) -> None:
    _reject_jwt_algorithm_none(auth.jwt_algorithm)

    algorithm = auth.jwt_algorithm or "RS256"

    if require_issuer_audience:
        if not auth.jwt_issuer:
            raise AuthConfigurationError("MCP_AUTH_JWT_ISSUER is required")
        if not auth.jwt_audience:
            raise AuthConfigurationError("MCP_AUTH_JWT_AUDIENCE is required")

    has_jwks = bool(auth.jwt_jwks_uri)
    has_key = bool(auth.jwt_public_key)
    if has_jwks and has_key:
        raise AuthConfigurationError(
            "Provide either MCP_AUTH_JWT_JWKS_URI or MCP_AUTH_JWT_PUBLIC_KEY, not both"
        )
    if not has_jwks and not has_key:
        raise AuthConfigurationError(
            "MCP_AUTH_JWT_JWKS_URI or MCP_AUTH_JWT_PUBLIC_KEY is required"
        )

    if auth.jwt_jwks_uri:
        _require_https_url(auth.jwt_jwks_uri, "MCP_AUTH_JWT_JWKS_URI")
        if algorithm.upper().startswith("HS"):
            raise AuthConfigurationError(
                "HMAC (HS*) algorithms cannot be used with MCP_AUTH_JWT_JWKS_URI"
            )

    if auth.jwt_public_key and "PRIVATE KEY" in auth.jwt_public_key:
        raise AuthConfigurationError(
            "MCP_AUTH_JWT_PUBLIC_KEY must not be a private key"
        )

    if algorithm.upper().startswith("HS"):
        secret = auth.jwt_public_key or ""
        if len(secret) < HMAC_MIN_SECRET_LENGTH:
            raise AuthConfigurationError(
                "HMAC secret in MCP_AUTH_JWT_PUBLIC_KEY must be at least "
                f"{HMAC_MIN_SECRET_LENGTH} characters"
            )


def _validate_introspection_fields(auth: MCPAuthConfig) -> None:
    if not auth.introspection_url:
        raise AuthConfigurationError("MCP_AUTH_INTROSPECTION_URL is required")
    _require_https_url(auth.introspection_url, "MCP_AUTH_INTROSPECTION_URL")
    if not auth.introspection_client_id:
        raise AuthConfigurationError("MCP_AUTH_INTROSPECTION_CLIENT_ID is required")
    if not auth.introspection_client_secret:
        raise AuthConfigurationError("MCP_AUTH_INTROSPECTION_CLIENT_SECRET is required")
    if not auth.introspection_issuer:
        raise AuthConfigurationError("MCP_AUTH_INTROSPECTION_ISSUER is required")
    if not auth.introspection_audience:
        raise AuthConfigurationError("MCP_AUTH_INTROSPECTION_AUDIENCE is required")
    if not auth.introspection_allowed_token_types:
        raise AuthConfigurationError(
            "MCP_AUTH_INTROSPECTION_ALLOWED_TOKEN_TYPES must not be empty"
        )
    if auth.introspection_auth_method not in (
        "client_secret_basic",
        "client_secret_post",
    ):
        raise AuthConfigurationError(
            "MCP_AUTH_INTROSPECTION_AUTH_METHOD must be client_secret_basic "
            "or client_secret_post"
        )


def _validate_token_backend(auth: MCPAuthConfig) -> None:
    # Bandit B105 reads "token_type" as a credential name. These compare
    # against verifier names from MCP_AUTH_TOKEN_TYPE, not secrets. Inline
    # suppressions are deliberately limited to the comparisons below.
    if auth.token_type == "jwt":  # nosec B105
        _validate_jwt_fields(auth, require_issuer_audience=True)
    elif auth.token_type == "introspection":  # nosec B105
        _validate_introspection_fields(auth)
    else:
        raise AuthConfigurationError("MCP_AUTH_TOKEN_TYPE must be jwt or introspection")


def _validate_redirect_uri_patterns(patterns: list[str]) -> None:
    for index, pattern in enumerate(patterns):
        normalized = pattern.strip()
        if not normalized:
            raise AuthConfigurationError(
                "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS must not contain empty entries"
            )
        lowered = normalized.casefold()
        if lowered.startswith(UNSAFE_REDIRECT_URI_SCHEMES):
            raise AuthConfigurationError(
                "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS["
                f"{index}] must not use an unsafe URI scheme"
            )
        host = _redirect_pattern_host(normalized)
        if not host or any(char in host for char in ("*", "?", "[")):
            raise AuthConfigurationError(
                "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS["
                f"{index}] must not use an unrestricted host pattern"
            )


def _validate_redis_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in ("redis", "rediss") or not parsed.hostname:
        raise AuthConfigurationError(
            "MCP_AUTH_REDIS_URL must be a redis:// or rediss:// URL"
        )


def _validate_storage_encryption_key(value: str) -> None:
    try:
        from cryptography.fernet import Fernet
    except ImportError as e:
        raise AuthConfigurationError(
            "MCP_AUTH_STORAGE_ENCRYPTION_KEY requires the cryptography package"
        ) from e
    try:
        Fernet(value.encode())
    except (ValueError, TypeError) as e:
        raise AuthConfigurationError(
            "MCP_AUTH_STORAGE_ENCRYPTION_KEY must be a Fernet key"
        ) from e


def _validate_storage_backend(auth: MCPAuthConfig) -> None:
    if auth.storage_backend not in VALID_STORAGE_BACKENDS:
        raise AuthConfigurationError("MCP_AUTH_STORAGE_BACKEND must be disk or redis")
    if not auth.is_proxy_mode():
        if (
            auth.storage_backend != "disk"
            or auth.storage_encryption_key
            or auth.redis_url
        ):
            raise AuthConfigurationError(
                "MCP_AUTH_STORAGE_BACKEND, MCP_AUTH_REDIS_URL, and "
                "MCP_AUTH_STORAGE_ENCRYPTION_KEY are only valid for "
                "oauth_proxy and oidc_proxy"
            )
        return
    if auth.storage_backend == "disk":
        if auth.redis_url:
            raise AuthConfigurationError(
                "MCP_AUTH_REDIS_URL is only valid with MCP_AUTH_STORAGE_BACKEND=redis"
            )
        if auth.storage_encryption_key:
            raise AuthConfigurationError(
                "MCP_AUTH_STORAGE_ENCRYPTION_KEY is only used with "
                "MCP_AUTH_STORAGE_BACKEND=redis; the default disk store is "
                "already encrypted from MCP_AUTH_JWT_SIGNING_KEY"
            )
        return
    if not auth.redis_url:
        raise AuthConfigurationError(
            "MCP_AUTH_REDIS_URL is required when MCP_AUTH_STORAGE_BACKEND=redis"
        )
    _validate_redis_url(auth.redis_url)
    if not auth.storage_encryption_key:
        raise AuthConfigurationError(
            "MCP_AUTH_STORAGE_ENCRYPTION_KEY is required when "
            "MCP_AUTH_STORAGE_BACKEND=redis so upstream tokens are not stored "
            "in plaintext"
        )
    _validate_storage_encryption_key(auth.storage_encryption_key)


def _validate_proxy_bind_rules(auth: MCPAuthConfig, bind_host: str) -> None:
    if not auth.is_proxy_mode():
        return
    loopback = is_loopback_bind(bind_host)
    if not loopback and not auth.jwt_signing_key:
        raise AuthConfigurationError(
            "MCP_AUTH_JWT_SIGNING_KEY is required when MCP_AUTH_MODE is "
            f"{auth.mode} and the bind address is not loopback"
        )
    if (
        auth.jwt_signing_key is not None
        and len(auth.jwt_signing_key) < JWT_SIGNING_KEY_MIN_LENGTH
    ):
        raise AuthConfigurationError(
            "MCP_AUTH_JWT_SIGNING_KEY must be at least "
            f"{JWT_SIGNING_KEY_MIN_LENGTH} characters"
        )
    if not loopback and auth.require_consent in ("false", "external"):
        raise AuthConfigurationError(
            "MCP_AUTH_REQUIRE_CONSENT=false/external is not allowed off-loopback"
        )
    if not loopback and auth.allowed_client_redirect_uris == []:
        raise AuthConfigurationError(
            "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS must not be empty off-loopback"
        )
    if auth.mode == "oidc_proxy" and not auth.forward_pkce:
        raise AuthConfigurationError(
            "MCP_AUTH_FORWARD_PKCE=false is not supported with MCP_AUTH_MODE=oidc_proxy"
        )


def _require_oauth_base_url(auth: MCPAuthConfig) -> None:
    if not auth.base_url:
        raise AuthConfigurationError("MCP_AUTH_BASE_URL is required")
    _require_https_url(auth.base_url, "MCP_AUTH_BASE_URL", allow_loopback_http=True)


def _validate_proxy_client(auth: MCPAuthConfig) -> None:
    if not auth.client_id:
        raise AuthConfigurationError("MCP_AUTH_CLIENT_ID is required")
    if not auth.client_secret and not auth.jwt_signing_key:
        raise AuthConfigurationError(
            "MCP_AUTH_CLIENT_SECRET is required unless a public PKCE client "
            "sets MCP_AUTH_JWT_SIGNING_KEY"
        )
    if auth.allowed_client_redirect_uris is None:
        auth.allowed_client_redirect_uris = list(DEFAULT_ALLOWED_CLIENT_REDIRECT_URIS)
    _validate_redirect_uri_patterns(auth.allowed_client_redirect_uris)
    _validate_storage_backend(auth)


def _validate_mode_fields(auth: MCPAuthConfig) -> None:
    if auth.mode == "none":
        _validate_storage_backend(auth)
        return
    _validate_ssrf_trust_proxy(auth)
    if auth.mode == "static_token":
        raise AuthConfigurationError(
            "MCP_AUTH_MODE=static_token is not supported. Use MCP_AUTH_MODE=token."
        )
    if auth.mode in ("token", "remote_oauth", "oauth_proxy"):
        _validate_token_backend(auth)
    if auth.mode == "token":
        _validate_storage_backend(auth)
    if auth.mode == "remote_oauth":
        if not auth.authorization_servers:
            raise AuthConfigurationError(
                "MCP_AUTH_AUTHORIZATION_SERVERS must be a non-empty JSON array"
            )
        for index, server in enumerate(auth.authorization_servers):
            _require_https_url(server, f"MCP_AUTH_AUTHORIZATION_SERVERS[{index}]")
        _require_oauth_base_url(auth)
        _validate_storage_backend(auth)
    if auth.mode == "oauth_proxy":
        if not auth.upstream_authorization_endpoint:
            raise AuthConfigurationError(
                "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT is required"
            )
        _require_https_url(
            auth.upstream_authorization_endpoint,
            "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT",
        )
        if not auth.upstream_token_endpoint:
            raise AuthConfigurationError("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT is required")
        _require_https_url(
            auth.upstream_token_endpoint, "MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT"
        )
        _require_oauth_base_url(auth)
        _validate_proxy_client(auth)
    if auth.mode == "oidc_proxy":
        if not auth.oidc_config_url:
            raise AuthConfigurationError("MCP_AUTH_OIDC_CONFIG_URL is required")
        _require_https_url(auth.oidc_config_url, "MCP_AUTH_OIDC_CONFIG_URL")
        _reject_jwt_algorithm_none(auth.jwt_algorithm)
        if auth.jwt_algorithm and auth.jwt_algorithm.upper().startswith("HS"):
            raise AuthConfigurationError(
                "HMAC (HS*) algorithms cannot be used with MCP_AUTH_MODE=oidc_proxy"
            )
        if not auth.oidc_verify_id_token and not auth.oidc_audience:
            raise AuthConfigurationError(
                "MCP_AUTH_OIDC_AUDIENCE is required when "
                "MCP_AUTH_OIDC_VERIFY_ID_TOKEN=false so access tokens are bound "
                "to this MCP Server"
            )
        _require_oauth_base_url(auth)
        _validate_proxy_client(auth)


def _parse_storage_backend() -> Literal["disk", "redis"]:
    raw = os.getenv("MCP_AUTH_STORAGE_BACKEND", "disk").strip().lower()
    if raw not in VALID_STORAGE_BACKENDS:
        raise AuthConfigurationError("MCP_AUTH_STORAGE_BACKEND must be disk or redis")
    return raw  # type: ignore[return-value]


def load_mcp_auth_config() -> MCPAuthConfig:
    """Parse MCP_AUTH_* and related TLS env vars. Does not apply HTTP fail-closed."""
    _reject_fastmcp_server_auth_env()

    mode_raw = os.getenv("MCP_AUTH_MODE", "none").strip().lower()
    if mode_raw not in VALID_MCP_AUTH_MODES:
        raise AuthConfigurationError(
            f"Invalid MCP_AUTH_MODE: {mode_raw}. Must be one of: {VALID_MCP_AUTH_MODES}"
        )
    if mode_raw not in IMPLEMENTED_MCP_AUTH_MODES:
        raise AuthConfigurationError(
            f"MCP_AUTH_MODE={mode_raw} is not supported. Use one of: "
            f"{list(IMPLEMENTED_MCP_AUTH_MODES)}."
        )

    token_type_raw = os.getenv("MCP_AUTH_TOKEN_TYPE", "jwt").strip().lower()
    if token_type_raw not in ("jwt", "introspection"):
        raise AuthConfigurationError("MCP_AUTH_TOKEN_TYPE must be jwt or introspection")

    introspection_method = (
        os.getenv("MCP_AUTH_INTROSPECTION_AUTH_METHOD", "client_secret_basic")
        .strip()
        .lower()
    )
    consent_raw = os.getenv("MCP_AUTH_REQUIRE_CONSENT", "true").strip().lower()
    if consent_raw not in ("true", "false", "remember", "external"):
        raise AuthConfigurationError(
            "MCP_AUTH_REQUIRE_CONSENT must be true, false, remember, or external"
        )

    redirect_path = os.getenv("MCP_AUTH_REDIRECT_PATH", "/auth/callback").strip()
    if (
        not redirect_path.startswith("/")
        or "//" in redirect_path
        or "://" in redirect_path
    ):
        raise AuthConfigurationError(
            "MCP_AUTH_REDIRECT_PATH must be a path (for example /auth/callback)"
        )

    scopes = _parse_json_string_list("MCP_AUTH_REQUIRED_SCOPES")
    if scopes is not None and len(scopes) == 0:
        scopes = None

    auth = MCPAuthConfig(
        mode=mode_raw,  # type: ignore[arg-type]
        http_auth=_get_auth_bool("MCP_HTTP_AUTH", True),
        allow_remote_sse=_get_auth_bool("MCP_ALLOW_REMOTE_SSE", False),
        tls_terminated=_get_auth_bool("MCP_TLS_TERMINATED", False),
        tls_certfile=os.getenv("MCP_TLS_CERTFILE") or None,
        tls_keyfile=os.getenv("MCP_TLS_KEYFILE") or None,
        token_type=token_type_raw,  # type: ignore[arg-type]
        token_leeway_seconds=_get_auth_int(
            "MCP_AUTH_TOKEN_LEEWAY_SECONDS", 60, minimum=0
        ),
        required_scopes=scopes,
        base_url=os.getenv("MCP_AUTH_BASE_URL") or None,
        jwt_jwks_uri=os.getenv("MCP_AUTH_JWT_JWKS_URI") or None,
        jwt_issuer=(os.getenv("MCP_AUTH_JWT_ISSUER") or "").strip() or None,
        jwt_audience=(os.getenv("MCP_AUTH_JWT_AUDIENCE") or "").strip() or None,
        jwt_algorithm=os.getenv("MCP_AUTH_JWT_ALGORITHM") or None,
        jwt_public_key=os.getenv("MCP_AUTH_JWT_PUBLIC_KEY") or None,
        introspection_url=os.getenv("MCP_AUTH_INTROSPECTION_URL") or None,
        introspection_client_id=os.getenv("MCP_AUTH_INTROSPECTION_CLIENT_ID") or None,
        introspection_client_secret=os.getenv("MCP_AUTH_INTROSPECTION_CLIENT_SECRET")
        or None,
        introspection_auth_method=introspection_method,  # type: ignore[arg-type]
        introspection_issuer=(os.getenv("MCP_AUTH_INTROSPECTION_ISSUER") or "").strip()
        or None,
        introspection_audience=(
            os.getenv("MCP_AUTH_INTROSPECTION_AUDIENCE") or ""
        ).strip()
        or None,
        introspection_allowed_token_types=[
            value.strip().casefold()
            for value in (
                _parse_json_string_list("MCP_AUTH_INTROSPECTION_ALLOWED_TOKEN_TYPES")
                or ["bearer", "access_token"]
            )
            if value.strip()
        ],
        introspection_allow_private=_get_auth_bool(
            "MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE", False
        ),
        jwks_allow_private=_get_auth_bool("MCP_AUTH_JWKS_ALLOW_PRIVATE", False),
        authorization_servers=_parse_json_string_list("MCP_AUTH_AUTHORIZATION_SERVERS"),
        upstream_authorization_endpoint=os.getenv(
            "MCP_AUTH_UPSTREAM_AUTHORIZATION_ENDPOINT"
        )
        or None,
        upstream_token_endpoint=os.getenv("MCP_AUTH_UPSTREAM_TOKEN_ENDPOINT") or None,
        oidc_config_url=os.getenv("MCP_AUTH_OIDC_CONFIG_URL") or None,
        oidc_audience=(os.getenv("MCP_AUTH_OIDC_AUDIENCE") or "").strip() or None,
        client_id=os.getenv("MCP_AUTH_CLIENT_ID") or None,
        client_secret=os.getenv("MCP_AUTH_CLIENT_SECRET") or None,
        jwt_signing_key=os.getenv("MCP_AUTH_JWT_SIGNING_KEY") or None,
        storage_encryption_key=os.getenv("MCP_AUTH_STORAGE_ENCRYPTION_KEY") or None,
        allowed_client_redirect_uris=_parse_json_string_list(
            "MCP_AUTH_ALLOWED_CLIENT_REDIRECT_URIS"
        ),
        require_consent=consent_raw,
        forward_pkce=_get_auth_bool("MCP_AUTH_FORWARD_PKCE", True),
        redirect_path=redirect_path,
        oidc_verify_id_token=_get_auth_bool("MCP_AUTH_OIDC_VERIFY_ID_TOKEN", False),
        storage_backend=_parse_storage_backend(),
        redis_url=os.getenv("MCP_AUTH_REDIS_URL") or None,
    )

    if auth.tls_certfile:
        auth.tls_certfile = auth.tls_certfile.strip() or None
    if auth.tls_keyfile:
        auth.tls_keyfile = auth.tls_keyfile.strip() or None

    _validate_tls_file_pair(auth.tls_certfile, auth.tls_keyfile)
    _validate_mode_fields(auth)
    return auth


def validate_http_auth_policy(
    transport: str, auth: MCPAuthConfig, bind_host: str | None = None
) -> None:
    """Apply transport, bind, and TLS fail-closed rules."""
    if not is_http_transport(transport):
        return

    host = bind_host if bind_host is not None else effective_bind_host()
    loopback = is_loopback_bind(host)
    in_process_tls = auth.has_in_process_tls()

    if auth.http_auth and auth.mode == "none":
        raise HttpAuthRequiredError(
            "HTTP MCP transports require authentication. Set MCP_AUTH_MODE "
            "(and the matching MCP_AUTH_* variables), or set MCP_HTTP_AUTH=false "
            "to keep unauthenticated HTTP."
        )

    if auth.is_real_mode() and not auth.http_auth:
        raise AuthConfigurationError(
            "MCP_HTTP_AUTH=false contradicts MCP_AUTH_MODE="
            f"{auth.mode}. Enable HTTP authentication or set MCP_AUTH_MODE=none."
        )

    if auth.is_real_mode() and not loopback and not in_process_tls:
        if not auth.tls_terminated:
            raise AuthConfigurationError(
                "HTTP MCP authentication on a non-loopback bind requires "
                "MCP_TLS_CERTFILE and MCP_TLS_KEYFILE, or MCP_TLS_TERMINATED=true "
                "when a reverse proxy or mesh terminates TLS."
            )

    _reject_wildcard_host_origin_allowlists()
    if transport == "sse" and not loopback and not auth.allow_remote_sse:
        raise AuthConfigurationError(
            "SSE on a non-loopback bind is refused because SSE has no Host/Origin "
            "protection. Use streamable-http, or set MCP_ALLOW_REMOTE_SSE=true "
            "as an explicit break-glass choice."
        )
    if transport != "sse":
        _validate_host_origin_policy(host)
    _validate_proxy_bind_rules(auth, host)


def validate_auth_for_transport(
    transport: str, auth: MCPAuthConfig | None = None, bind_host: str | None = None
) -> MCPAuthConfig:
    """Load (if needed) and validate auth for the transport that will be started."""
    if not is_http_transport(transport):
        return MCPAuthConfig()
    config = auth if auth is not None else load_mcp_auth_config()
    validate_http_auth_policy(transport, config, bind_host=bind_host)
    return config


class ConfigValidator:
    """Validates and loads configuration from environment variables."""

    @staticmethod
    def parse_hosts(hosts_json: str) -> list[HostConfig]:
        """Parse and validate hosts from JSON string."""
        try:
            hosts_data = json.loads(hosts_json)
        except json.JSONDecodeError as e:
            raise ConfigurationError(f"Invalid JSON in REDFISH_HOSTS: {e}") from e

        if not isinstance(hosts_data, list):
            raise ConfigurationError("REDFISH_HOSTS must be a JSON array")

        hosts = []
        for i, host_data in enumerate(hosts_data):
            if not isinstance(host_data, dict):
                raise ConfigurationError(f"Host {i} must be a JSON object")

            try:
                host = HostConfig(**host_data)
                hosts.append(host)
            except (TypeError, ValueError) as e:
                raise ConfigurationError(
                    f"Invalid host configuration at index {i}: {e}"
                ) from e

        return hosts

    @staticmethod
    def get_env_bool(key: str, default: bool = False) -> bool:
        """Get boolean value from environment variable."""
        value = os.getenv(key)
        if value is None:
            return default

        normalized = value.lower()
        if normalized in ("true", "1", "yes", "on"):
            return True
        if normalized in ("false", "0", "no", "off"):
            return False
        raise ConfigurationError(f"Environment variable {key} must be a boolean value")

    @staticmethod
    def get_env_int(
        key: str, default: int, min_val: int | None = None, max_val: int | None = None
    ) -> int:
        """Get integer value from environment variable with optional bounds checking."""
        try:
            value = int(os.getenv(key, str(default)))
        except ValueError:
            raise ConfigurationError(
                f"Environment variable {key} must be an integer"
            ) from None

        if min_val is not None and value < min_val:
            raise ConfigurationError(
                f"Environment variable {key} must be >= {min_val}, got: {value}"
            )

        if max_val is not None and value > max_val:
            raise ConfigurationError(
                f"Environment variable {key} must be <= {max_val}, got: {value}"
            )

        return value

    @classmethod
    def load_config(cls) -> tuple[RedfishConfig, MCPConfig]:
        """Load and validate complete configuration from environment variables."""
        try:
            # Parse hosts
            hosts_json = os.getenv("REDFISH_HOSTS", '[{"address": "127.0.0.1"}]')
            hosts = cls.parse_hosts(hosts_json)

            # Build Redfish configuration
            redfish_config = RedfishConfig(
                hosts=hosts,
                port=cls.get_env_int("REDFISH_PORT", 443, 1, 65535),
                auth_method=os.getenv("REDFISH_AUTH_METHOD", AuthMethod.SESSION),
                username=os.getenv("REDFISH_USERNAME", ""),
                password=os.getenv("REDFISH_PASSWORD", ""),
                tls_server_ca_cert=os.getenv("REDFISH_SERVER_CA_CERT"),
                tls_verify=cls.get_env_bool("REDFISH_TLS_VERIFY", True),
                discovery_enabled=cls.get_env_bool("REDFISH_DISCOVERY_ENABLED", False),
                discovery_interval=cls.get_env_int("REDFISH_DISCOVERY_INTERVAL", 30, 1),
            )

            # Build MCP configuration
            transport_str = os.getenv("MCP_TRANSPORT", "stdio")
            if transport_str not in VALID_MCP_TRANSPORTS:
                raise ConfigurationError(
                    f"Invalid transport: {transport_str}. Must be one of: {VALID_MCP_TRANSPORTS}"
                )
            if is_http_transport(transport_str):
                auth_config = load_mcp_auth_config()
                validate_http_auth_policy(transport_str, auth_config)
            else:
                # stdio is process-isolated and does not use MCP HTTP auth,
                # listen-socket TLS, or FastMCP HTTP provider settings.
                auth_config = MCPAuthConfig()
            mcp_config = MCPConfig(
                transport=transport_str,  # type: ignore[arg-type]
                log_level=os.getenv("MCP_REDFISH_LOG_LEVEL", "INFO"),
                auth=auth_config,
            )

            logger.info(
                f"Configuration loaded successfully: {len(redfish_config.hosts)} hosts, "
                f"transport: {mcp_config.transport}, auth_mode: {auth_config.mode}"
            )
            return redfish_config, mcp_config

        except Exception as e:
            if isinstance(e, ConfigurationError):
                raise
            else:
                raise ConfigurationError(f"Failed to load configuration: {e}") from e


def load_validated_config() -> tuple[RedfishConfig, MCPConfig]:
    """Load and validate configuration.

    Raises ConfigurationError. Reporting is the caller's job; a caller that
    loads configuration during import should use fatal_configuration_error so
    the operator sees the message instead of an import traceback.
    """
    try:
        return ConfigValidator.load_config()
    except ConfigurationError:
        raise
    except Exception as e:
        raise ConfigurationError(
            f"Failed to load configuration due to unexpected error: {e}"
        ) from e


def fatal_configuration_error(error: ConfigurationError) -> SystemExit:
    """Report a fatal configuration error and return the exit to raise.

    This project loads and validates configuration while `src.common` is
    imported, so letting the exception escape buries the one line the operator
    needs under an import traceback. Raising the returned SystemExit prints
    nothing further and still exits non-zero.
    """
    logger.error("Configuration error: %s", redact_sensitive_text(str(error)))
    if isinstance(error, HttpAuthRequiredError):
        logger.error("%s", MCP_AUTH_BREAKING_CHANGE_HINT)
    logger.error("Check your environment variables and .env file, then retry.")
    return SystemExit(1)
