# Manual identity-provider checks

Use this checklist to test with your real identity provider (IdP). An IdP is the
service that creates and validates access tokens, such as Keycloak, Auth0, or
Okta.

These checks are not required by continuous integration (CI). Automated tests
already cover local JWTs, a local HTTPS introspection service, HTTP
Host/Origin protection, Remote OAuth metadata routes, OAuth Proxy login against
a loopback OpenID simulator in the integration suite, and OAuth Proxy, OIDC
Proxy, and Remote OAuth against CNCF Dex (including OIDC access-token
verification and Dex JWT Bearer without MCP-client DCR). A real cloud IdP needs
organization-specific accounts, secrets, and network access. GitHub, Azure, and
Auth0 can differ from Dex in token format, discovery fields, and consent.

Before choosing an IdP, read [Identity provider requirements](./MCP_AUTH.md#identity-provider-requirements)
in the authentication guide. Browser login modes only work when the IdP issues
JWT access tokens (JWKS or a fixed public key), opaque tokens plus an
introspection endpoint the MCP Server can call, or — for `oidc_proxy` only — a
signed OIDC ID token when access tokens are opaque.

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

## Check Remote OAuth

1. Set `MCP_AUTH_MODE=remote_oauth` and the JWT or introspection variables from
   the sections above.
2. Set `MCP_AUTH_AUTHORIZATION_SERVERS` to a JSON array of HTTPS issuer URLs.
3. Set `MCP_AUTH_BASE_URL` to this MCP Server's public origin.
4. `GET /.well-known/oauth-protected-resource/mcp` without a Bearer token.
   Expect HTTP 200. This route is public by design.
5. Call `list_servers` without a token. Expect HTTP 401.
6. Complete the identity provider login (DCR) in a real MCP client, then call
   `list_servers` with the issued Bearer token.

Do not automate this browser login in CI.

## Check OAuth Proxy

1. Register a fixed OAuth application with the identity provider. Set the
   redirect URI to `{MCP_AUTH_BASE_URL}/auth/callback` (or your custom
   `MCP_AUTH_REDIRECT_PATH`).
2. Set `MCP_AUTH_MODE=oauth_proxy`, the upstream authorize/token HTTPS URLs,
   `MCP_AUTH_CLIENT_ID`, and `MCP_AUTH_CLIENT_SECRET`.
3. Configure upstream token verification (JWT or introspection) as for
   `MCP_AUTH_MODE=token`. The upstream access token must be a JWT or an
   introspectable opaque token. GitHub access tokens are neither.
4. Off-loopback, also set `MCP_AUTH_JWT_SIGNING_KEY` and TLS as in
   [MCP_HTTP_DEPLOYMENT.md](./MCP_HTTP_DEPLOYMENT.md).
5. `GET /.well-known/oauth-authorization-server` without a Bearer token.
   Expect HTTP 200.
6. Call `list_servers` without login. Expect HTTP 401.
7. Complete the consent page and identity provider redirect in a real MCP
   client, then call `list_servers`.

Automated e2e covers this mode against CNCF Dex (fixed static client, JWT
JWKS or introspection). Remote OAuth Dex coverage (protected-resource metadata
and Bearer from a direct Dex login) is in the same suite. Do not automate
GitHub, Google, or Auth0 login in CI.

## Check OIDC Proxy

1. Set `MCP_AUTH_MODE=oidc_proxy` and
   `MCP_AUTH_OIDC_CONFIG_URL` to the HTTPS
   `/.well-known/openid-configuration` URL.
2. Set `MCP_AUTH_CLIENT_ID`, `MCP_AUTH_CLIENT_SECRET`, and `MCP_AUTH_BASE_URL`.
3. Set `MCP_AUTH_OIDC_AUDIENCE` to this MCP Server's audience unless you set
   `MCP_AUTH_OIDC_VERIFY_ID_TOKEN=true` (opaque access tokens; audience is then
   the client id).
4. Set `MCP_AUTH_OIDC_VERIFY_ID_TOKEN=true` if access tokens are opaque and
   the ID token should be verified instead.
5. Off-loopback, set `MCP_AUTH_JWT_SIGNING_KEY` and TLS as for OAuth Proxy.
6. Confirm discovery metadata is reachable without a Bearer token, then confirm
   `list_servers` fails without login and succeeds after the OIDC redirect.

Do not automate this browser login in CI.
