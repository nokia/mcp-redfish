# Changelog

All notable changes to this project are documented in this file.

## Unreleased

### Breaking change

HTTP MCP transports (`sse`, `streamable-http`) now require authentication. Set `MCP_AUTH_MODE` (and the matching `MCP_AUTH_*` variables), or set `MCP_HTTP_AUTH=false` to keep unauthenticated HTTP. stdio is unchanged. See README and the release notes.

Old `make run-sse` / `make run-streamable-http` / `MCP_TRANSPORT=sse` without the new env **will not start**. Migration is either configure `MCP_AUTH_MODE` or set `MCP_HTTP_AUTH=false`.

This is a security hardening change on a `0.1.0` tree; it is still spelled out as a break because HTTP was documented as a supported remote mode.

### Breaking change: configuration errors abort

Configuration that fails validation now logs the error and exits non-zero. The legacy fallback parser is removed. Previously a rejected configuration produced a deprecation warning and the server continued with substituted defaults — a malformed `REDFISH_HOSTS` became `[{"address": "127.0.0.1"}]`, an unparseable `REDFISH_TLS_VERIFY` was forced back to enabled, and an unrecognised `MCP_TRANSPORT` was passed through unvalidated.

That last case also let `MCP_TRANSPORT=http` (a transport name FastMCP accepts) start an unauthenticated HTTP listener despite `MCP_HTTP_AUTH` defaulting to `true`. The HTTP fail-closed, bind, and TLS rules now apply to every transport that is not `stdio`, rather than to an allowlist of `sse` and `streamable-http`.

### Added

- Fail-closed MCP HTTP authentication (Phase 0) with explicit bind (`FASTMCP_HOST` unset → `127.0.0.1`) and listen-socket TLS (`MCP_TLS_CERTFILE`/`MCP_TLS_KEYFILE` or `MCP_TLS_TERMINATED`).
- Token verification (Phase 1): `JWTVerifier` (JWKS or public key, issuer and audience required) and `IntrospectionTokenVerifier`.
- Authentication guide: [docs/MCP_AUTH.md](docs/MCP_AUTH.md). HTTP deployment
  and listener guide: [docs/MCP_HTTP_DEPLOYMENT.md](docs/MCP_HTTP_DEPLOYMENT.md).
  Manual IdP checklist: [docs/MCP_AUTH_MANUAL_IDP.md](docs/MCP_AUTH_MANUAL_IDP.md).
- HTTP e2e coverage for `MCP_HTTP_AUTH=false` (warning + tools) and local JWT Bearer (unauthenticated call fails; authenticated `list_servers` works). Default e2e remains stdio.
- Startup refuses `*` in `FASTMCP_HTTP_ALLOWED_HOSTS`/`FASTMCP_HTTP_ALLOWED_ORIGINS`, which would disable the Host/Origin guard that protects HTTP transports from DNS rebinding. Checked against the effective FastMCP settings, so a value supplied through `FASTMCP_ENV_FILE` is caught too. Joins the existing refusal of `FASTMCP_SERVER_AUTH*`. See [docs/MCP_HTTP_DEPLOYMENT.md](docs/MCP_HTTP_DEPLOYMENT.md).
- `FASTMCP_SSRF_TRUST_PROXY=true` is supported for deployments that can only reach their identity provider through an enterprise proxy, and is validated rather than refused: enabling it without `HTTPS_PROXY` or `ALL_PROXY` now aborts at startup, because FastMCP would otherwise refuse every JWKS and OAuth metadata fetch at the first token verification. Startup logs a warning naming the proxy variable in use, never its value. The default (`ssrf_safe=True` with DNS resolution and the address blocklist) already works behind a proxy and remains preferred; see the new "Reaching the identity provider through an enterprise proxy" section of [docs/MCP_AUTH.md](docs/MCP_AUTH.md).
- Security review of the authentication work: [docs/MCP_AUTH_REVIEW.md](docs/MCP_AUTH_REVIEW.md).
- Post-verification token policy around FastMCP providers: JWTs now require
  `exp` and enforce `nbf`/future `iat`; introspection requires matching issuer,
  audience, and access-token type.
- SSRF-safe, DNS-pinned introspection POSTs with explicit
  `MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true` for deliberately private IdPs.
- Strict Host/Origin protection by default on non-loopback Streamable HTTP
  binds, with exact `FASTMCP_HTTP_ALLOWED_HOSTS`.

### Fixed

- Configuration errors are reported as a single `Configuration error: …` line instead of an import traceback. Configuration is validated while `src.common` is imported, so the previous handler in `RedfishMCPServer.run()` was unreachable and every rejected value — including an ordinary `REDFISH_HOSTS` typo — printed a stack trace above the message. The breaking-change migration text is now emitted with the fail-closed HTTP error specifically, rather than with every auth error.
- A server that fails to start exits non-zero. `mcp.run()` failures were logged and swallowed, so a process that never bound its port reported success to its supervisor.
- FastMCP's own rejections of an `MCP_AUTH_*` combination (an `HS*` algorithm paired with a PEM public key, for example) are reported as configuration errors rather than a `ValueError` traceback from provider construction.
- Docker images copy only runtime project files, preventing local `.env`,
  certificates, tests, and workspace artifacts from entering image layers.
- stdio now ignores HTTP authentication settings instead of constructing or
  rejecting unused providers.
- Bracketed IPv6 loopback binds are normalized; wildcard-like Host/Origin
  patterns are refused; tools consume the validated Redfish host list.
- HTTP integration servers shut down cleanly, HTTP e2e scrubs inherited auth
  variables, and negative Inspector tests no longer pass on connection timeout.
- Non-loopback SSE is refused by default because SSE has no Host/Origin
  protection. Legacy deployments must explicitly set the warned
  `MCP_ALLOW_REMOTE_SSE=true` break-glass setting.
- Startup logs now report safe effective configuration fields, and DEBUG logs
  provide stable token-rejection and identity-provider egress reason codes.
  FastMCP provider logs are sanitized so tokens, claims, credentials, response
  bodies, key contents, scope names, and proxy URLs are not emitted.

### GitHub Release notes (draft)

Title the section **Breaking change**. Include:

- HTTP transports now require authentication; stdio is unchanged.
- Old `make run-sse` / `make run-streamable-http` / `MCP_TRANSPORT=sse` without new env will not start.
- Migration: configure `MCP_AUTH_MODE` or set `MCP_HTTP_AUTH=false`.
- See README and [docs/MCP_AUTH.md](docs/MCP_AUTH.md).
