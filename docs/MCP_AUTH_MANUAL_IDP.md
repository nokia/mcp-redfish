# Manual identity-provider checks

Use this checklist to test with your real identity provider (IdP). An IdP is the
service that creates and validates access tokens, such as Keycloak, Auth0, or
Okta.

These checks are not required by continuous integration (CI). Automated tests
already cover local JWTs, a local HTTPS introspection service, and HTTP
Host/Origin protection. A real IdP needs organization-specific accounts,
secrets, and network access.

Remote OAuth, OAuth Proxy, and OIDC Proxy are not implemented in this release.

## Before you start

- Use a test environment, not a production BMC.
- Never paste tokens, client secrets, or BMC passwords into logs or issue
  reports.
- HTTP status `401 Unauthorized` means the MCP server did not accept the
  client's token.
- `list_servers` is the simplest MCP tool to use for a successful test.

## Check a JWT

1. Set `MCP_TRANSPORT=streamable-http` and `MCP_AUTH_MODE=token`.
2. Choose one way to verify token signatures:

   **Option A — JWKS URL (recommended)**

   Most identity providers publish an OpenID configuration document. Open this
   URL, replacing the example hostname with your issuer:

   ```text
   https://idp.example.com/.well-known/openid-configuration
   ```

   Find the `jwks_uri` value in that document. Set it as:

   ```bash
   export MCP_AUTH_JWT_JWKS_URI=https://idp.example.com/.well-known/jwks.json
   ```

   Your IdP administrator or IdP documentation can also provide this URL. It
   must use HTTPS.

   **Option B — fixed public key**

   Ask the IdP administrator for the public key that verifies access-token
   signatures. Save the PEM public key in a protected local file, then load it:

   ```bash
   export MCP_AUTH_JWT_PUBLIC_KEY="$(cat /secure/path/mcp-public-key.pem)"
   ```

   The file should start with `-----BEGIN PUBLIC KEY-----`. Never provide the
   IdP's private signing key.

   Set only one of `MCP_AUTH_JWT_JWKS_URI` and
   `MCP_AUTH_JWT_PUBLIC_KEY`. The MCP Server rejects a configuration that sets
   both.
3. Set `MCP_AUTH_JWT_ISSUER` to the exact token issuer (`iss`).
4. Set `MCP_AUTH_JWT_AUDIENCE` to the expected service audience (`aud`).
5. On a laptop, keep the default local address. For a remote address, also
   configure TLS and exact `FASTMCP_HTTP_ALLOWED_HOSTS` as described in
   [MCP_HTTP_DEPLOYMENT.md](./MCP_HTTP_DEPLOYMENT.md).
6. Call the MCP endpoint without an `Authorization` header. Expect HTTP 401.
7. Call it with `Authorization: Bearer <jwt>`. A valid, unexpired token with the
   correct issuer and audience should allow `list_servers`.
8. Repeat with an expired token, a token for another audience, and an unsigned
   string. Each request should return HTTP 401.

## Check token introspection

1. Set `MCP_AUTH_MODE=token` and `MCP_AUTH_TOKEN_TYPE=introspection`.
2. Set the HTTPS introspection URL and its client ID and client secret.
3. Set `MCP_AUTH_INTROSPECTION_ISSUER` and
   `MCP_AUTH_INTROSPECTION_AUDIENCE` to the values returned for this MCP
   service.
4. If the IdP has a private network address, set
   `MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true`. Confirm that the startup warning
   describes the private IdP trust decision.
5. A request without a token should return HTTP 401.
6. An active access token with the correct issuer and audience should allow
   `list_servers`.
7. Inactive, revoked, wrong-audience, and refresh tokens should return HTTP 401.

## Lab HTTP without an IdP

1. Set `MCP_TRANSPORT=streamable-http` and `MCP_HTTP_AUTH=false`.
2. Keep the default local address (`127.0.0.1`).
3. Confirm that startup logs the authentication-disabled warning.
4. Confirm that tools work without a Bearer token.

Use this setup only for a temporary local lab. Any client that can reach the
port can use the configured Redfish credentials.

## Later phases (not implemented)

When Remote OAuth / OAuth Proxy / OIDC Proxy ship, add per-mode steps here: env vars, expected 401 without login, success after the IdP redirect, and metadata routes that stay public by design (`/.well-known/…`).
