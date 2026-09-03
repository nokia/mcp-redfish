# MCP HTTP authentication

This guide explains how to control who can use the MCP server over a network.
It is written for operators. You do not need to be an OAuth expert.

If the MCP server runs as a local child process with `stdio`, HTTP
authentication does not apply. The server ignores all `MCP_AUTH_*` settings in
that mode.

**Breaking change:** HTTP MCP transports (`sse`, `streamable-http`) now require authentication. Set `MCP_AUTH_MODE` (and the matching `MCP_AUTH_*` variables), or set `MCP_HTTP_AUTH=false` to keep unauthenticated HTTP. stdio is unchanged. See README and the release notes.

Remote OAuth, OAuth Proxy, and OIDC Proxy are specified in [MCP_AUTH_PLAN.md](./MCP_AUTH_PLAN.md) (Phases 2–4) and are **not implemented** in this release. `MCP_AUTH_MODE` values other than `none` and `token` are rejected.

## Start here

Choose the row that matches your use:

| Your use | Recommended setting |
| --- | --- |
| A local MCP client starts this server as a child process | Use `MCP_TRANSPORT=stdio`. This is the default. |
| A temporary local lab needs HTTP and has no token service | Use `MCP_TRANSPORT=streamable-http` and `MCP_HTTP_AUTH=false`. Keep the default loopback address. |
| A production service already issues JWT access tokens | Use `MCP_AUTH_MODE=token` and `MCP_AUTH_TOKEN_TYPE=jwt`. This is the preferred production option. |
| A production service issues opaque tokens, not JWTs | Use `MCP_AUTH_MODE=token` and `MCP_AUTH_TOKEN_TYPE=introspection`. The identity provider must offer a token introspection endpoint. |
| Users must sign in through a browser | This is not supported in this release. Remote OAuth and proxy modes are planned for later phases. |

For remote HTTP, prefer `streamable-http` instead of `sse`.

## Important: one valid token gives access to every configured BMC

A valid MCP token may call **every** tool against **every** configured BMC, using the shared `REDFISH_*` service account. This MCP Server does not map an IdP user to a BMC user. Empty `MCP_AUTH_REQUIRED_SCOPES` means any authenticated token, which is full BMC access through this server.

Never copy the MCP `Authorization` header (or an IdP access token) onto Redfish calls. BMC credentials stay `REDFISH_*` only.

In plain terms: MCP authentication checks whether a client may use this server.
Redfish authentication is the separate username and password that this server
uses to connect to each managed machine.

## Terms used in this guide

- **Authentication (auth):** checking that a client is allowed to connect.
- **Authorization:** deciding what an authenticated client may do. This release
  does not provide different permissions for different users.
- **MCP:** Model Context Protocol. It is the protocol used by the AI client to
  call this server's tools.
- **Redfish:** the management API used to control servers and other hardware.
- **BMC:** Baseboard Management Controller. It is the management controller in
  a physical server.
- **Identity provider (IdP):** the service that creates tokens and confirms
  identities. Examples include Keycloak, Auth0, and Okta.
- **OAuth:** a standard framework for giving applications limited access with
  tokens instead of sharing a user's password.
- **OIDC:** OpenID Connect, an identity layer built on OAuth.
- **FastMCP:** the Python framework used by this project to run the MCP server
  and perform the core token checks.
- **Access token:** a short-lived credential sent by an MCP client.
- **Bearer token:** an access token sent in the HTTP `Authorization` header.
  Anyone who has the token can use it until it expires.
- **JWT:** JSON Web Token. A signed token that the MCP server can check locally.
- **Issuer (`iss`):** the identity provider that created a token.
- **Audience (`aud`):** the service that a token was created for. For this
  project, it should identify this MCP server.
- **JWKS:** JSON Web Key Set. A secure HTTPS endpoint where an identity provider
  publishes public keys used to verify JWT signatures.
- **PEM:** a common text format for cryptographic keys and certificates. PEM
  values usually contain lines such as `-----BEGIN PUBLIC KEY-----`.
- **HMAC:** a signature method that uses the same shared secret to create and
  verify a signature.
- **Introspection:** asking the identity provider whether an opaque token is
  active and what it is allowed to access.
- **Scope:** a permission name inside a token, such as `mcp:read`.
- **SSRF:** Server-Side Request Forgery. An attack that tricks a server into
  sending a request, and sometimes credentials, to an unintended address.

For protocol-level details, see the maintainer-focused
[authentication plan](./MCP_AUTH_PLAN.md) and
[security review](./MCP_AUTH_REVIEW.md).
Listener and network terms are explained in
[MCP HTTP deployment and listener security](./MCP_HTTP_DEPLOYMENT.md).

## Fail-closed HTTP

The server is **fail closed**. This means it stops during startup when HTTP
authentication is missing or invalid. It does not start an unprotected network
service by accident.

`MCP_HTTP_AUTH` defaults to `true`. This setting controls client
authentication. It does not enable HTTPS or encrypt traffic.

| Transport | Rule |
| --- | --- |
| `stdio` | No MCP HTTP auth. `MCP_HTTP_AUTH` is ignored. |
| `streamable-http` / `sse` | Refuse to start unless a real `MCP_AUTH_MODE` is set, or `MCP_HTTP_AUTH=false`. |

Use `streamable-http` for HTTP deployments. `MCP_TRANSPORT` accepts only
`stdio`, `streamable-http`, and `sse`. Any other value is rejected.
Non-loopback SSE is also refused unless the operator explicitly enables the
warned `MCP_ALLOW_REMOTE_SSE=true` break-glass setting. See
[MCP_HTTP_DEPLOYMENT.md](./MCP_HTTP_DEPLOYMENT.md).

The server also rejects conflicting settings. For example, it will not accept
both a real authentication mode and `MCP_HTTP_AUTH=false`.

When `MCP_HTTP_AUTH=false`, this MCP Server logs this warning once:

```
WARNING: MCP HTTP authentication is disabled (MCP_HTTP_AUTH=false). Any client that can reach this MCP Server can call MCP tools using the configured Redfish credentials. Listening on FASTMCP_HOST=<addr> port <port>.
```

Do not place the local `stdio` server behind another tool that exposes it over
HTTP without authentication. Use this project's HTTP transport for remote
access.

## Configure the HTTP listener separately

Authentication decides **who** may use this MCP Server. Listener configuration
decides **where** it accepts connections and **how** network traffic is
protected.

See [MCP HTTP deployment and listener security](./MCP_HTTP_DEPLOYMENT.md) for:

- `FASTMCP_HOST` and `FASTMCP_PORT`;
- Host and Origin protection;
- TLS certificates and `MCP_TLS_TERMINATED`;
- reverse proxies and service meshes; and
- Docker and Kubernetes deployment.

Complete both guides before exposing this MCP Server outside the local machine.

## Token verification (`MCP_AUTH_MODE=token`)

Choose how the server checks access tokens:

- `jwt` is the default. The server verifies a signed token locally.
- `introspection` asks the identity provider about every token.

### JWT (preferred)

JWT is usually the simplest production option. The identity provider signs each
token with a private key. This server verifies the signature with a public key.
The private signing key must remain in the identity provider.

Clients send the token in this header:

```http
Authorization: Bearer <jwt>
```

Required:

- `MCP_AUTH_JWT_ISSUER`: the expected token creator. It must exactly match the
  token's `iss` value.
- `MCP_AUTH_JWT_AUDIENCE`: the name of this MCP service. It must match the
  token's `aud` value.
- One source of verification keys:
  - `MCP_AUTH_JWT_JWKS_URI`: an HTTPS URL where the identity provider publishes
    public keys. This is preferred because it supports key rotation.
  - `MCP_AUTH_JWT_PUBLIC_KEY`: a fixed public key in PEM text format.

#### How to find the JWKS URL or public key

Most identity providers publish an OpenID configuration document at:

```text
https://<your-issuer>/.well-known/openid-configuration
```

Open that document and find its `jwks_uri` value. Use the complete HTTPS URL as
`MCP_AUTH_JWT_JWKS_URI`. Your identity provider's documentation or
administrator can also provide the correct URL.

If the identity provider does not publish JWKS, ask its administrator for the
public key used to verify access-token signatures. Save the PEM public key in a
protected file and load it into the environment:

```bash
export MCP_AUTH_JWT_PUBLIC_KEY="$(cat /secure/path/mcp-public-key.pem)"
```

The file should start with `-----BEGIN PUBLIC KEY-----`. Never copy a private
signing key to the MCP Server. Set either `MCP_AUTH_JWT_JWKS_URI` or
`MCP_AUTH_JWT_PUBLIC_KEY`, not both.

HMAC (`HS*`) uses one shared secret instead of a public/private key pair. It is
allowed only without JWKS, and the secret must contain at least 32 characters.
Asymmetric keys and JWKS are safer for most deployments. The unsafe `none`
algorithm and private keys in `MCP_AUTH_JWT_PUBLIC_KEY` are rejected.

The server also checks the token times:

- `exp` is the expiry time. It is required and must be in the future.
- `nbf` means “not before.” The token cannot be used before this time.
- `iat` is the issue time. It cannot be unreasonably far in the future.

`MCP_AUTH_TOKEN_LEEWAY_SECONDS` allows for small clock differences between
machines. Its default is 60 seconds. Tokens without a valid future expiry are
rejected.

Example:

```bash
export MCP_TRANSPORT=streamable-http
export MCP_AUTH_MODE=token
export MCP_AUTH_TOKEN_TYPE=jwt
export MCP_AUTH_JWT_JWKS_URI=https://idp.example.com/.well-known/jwks.json
export MCP_AUTH_JWT_ISSUER=https://idp.example.com/
export MCP_AUTH_JWT_AUDIENCE=mcp-redfish
# FASTMCP_HOST unset → 127.0.0.1 (loopback, TLS optional)
```

A request without a Bearer token is rejected (HTTP 401).

### Introspection

Use introspection when clients receive opaque tokens that this server cannot
verify by itself. For each client request, the MCP server sends the token to the
identity provider over HTTPS. The identity provider replies that the token is
active or inactive.

The MCP server authenticates this check with its own introspection client ID and
secret. These credentials are different from the incoming Bearer token.

```bash
export MCP_AUTH_MODE=token
export MCP_AUTH_TOKEN_TYPE=introspection
export MCP_AUTH_INTROSPECTION_URL=https://idp.example.com/oauth/introspect
export MCP_AUTH_INTROSPECTION_CLIENT_ID=mcp-redfish
export MCP_AUTH_INTROSPECTION_CLIENT_SECRET=...   # env/file, never argv
export MCP_AUTH_INTROSPECTION_ISSUER=https://idp.example.com/
export MCP_AUTH_INTROSPECTION_AUDIENCE=mcp-redfish
# optional: MCP_AUTH_INTROSPECTION_AUTH_METHOD=client_secret_basic|client_secret_post
```

The introspection URL must use HTTPS. A response is accepted only when:

- the identity provider says the token is active;
- `iss` matches `MCP_AUTH_INTROSPECTION_ISSUER`;
- `aud` includes `MCP_AUTH_INTROSPECTION_AUDIENCE`; and
- `token_type` or `token_use` identifies an access token, not a refresh token.

By default, the server blocks introspection requests to local and private
network addresses. This reduces the risk that a wrong or compromised hostname
sends tokens and client credentials to an unintended internal service. It also
does not follow redirects and rejects unusually large responses.

Some organizations run their identity provider only on a private network. In
that case, set `MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true`. The server logs a
warning because you are explicitly trusting the configured hostname, internal
DNS, and network routing. HTTPS is still required.

## Environment reference

| Variable | Default | Notes |
| --- | --- | --- |
| `MCP_HTTP_AUTH` | `true` | MCP client auth on HTTP. Not TLS. Ignored on stdio. |
| `MCP_AUTH_MODE` | `none` | `none` or `token` in this release. |
| `MCP_AUTH_TOKEN_TYPE` | `jwt` | `jwt` or `introspection`. |
| `MCP_AUTH_TOKEN_LEEWAY_SECONDS` | `60` | Clock skew for JWT `nbf` and `iat`; non-negative integer. |
| `MCP_AUTH_JWT_JWKS_URI` | unset | HTTPS JWKS URL. |
| `MCP_AUTH_JWT_ISSUER` | unset | Required for JWT. |
| `MCP_AUTH_JWT_AUDIENCE` | unset | Required for JWT. |
| `MCP_AUTH_JWT_ALGORITHM` | provider default (RS256) | `none` is refused. |
| `MCP_AUTH_JWT_PUBLIC_KEY` | unset | PEM public key or HMAC secret. |
| `MCP_AUTH_INTROSPECTION_URL` | unset | HTTPS. |
| `MCP_AUTH_INTROSPECTION_CLIENT_ID` | unset | Required for introspection. |
| `MCP_AUTH_INTROSPECTION_CLIENT_SECRET` | unset | Required for introspection. |
| `MCP_AUTH_INTROSPECTION_AUTH_METHOD` | `client_secret_basic` | or `client_secret_post`. |
| `MCP_AUTH_INTROSPECTION_ISSUER` | unset | Required; must match introspection response `iss`. |
| `MCP_AUTH_INTROSPECTION_AUDIENCE` | unset | Required; must match response `aud` string/list. |
| `MCP_AUTH_INTROSPECTION_ALLOWED_TOKEN_TYPES` | `["Bearer","access_token"]` | Non-empty JSON list; refresh tokens are rejected. |
| `MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE` | `false` | Explicitly trust a private IdP’s HTTPS endpoint and internal DNS/routing; warns. |
| `MCP_AUTH_REQUIRED_SCOPES` | empty | JSON array of strings. Empty = any authenticated token. |

Listener variables are listed in
[MCP HTTP deployment and listener security](./MCP_HTTP_DEPLOYMENT.md).

## Advanced: FastMCP authentication settings this project refuses

FastMCP can read additional authentication settings from the environment. This
project rejects them because they could create a second authentication
configuration:

| Setting | Why it is refused |
| --- | --- |
| `FASTMCP_SERVER_AUTH`, `FASTMCP_SERVER_AUTH_*` | These could create a second authentication configuration. Use only `MCP_AUTH_*` settings. |

These settings are checked even when they come from `FASTMCP_ENV_FILE`.

## Advanced: reaching the identity provider through a company proxy

A company proxy is a service that controls outbound network connections. Most
deployments do not need special settings: the default JWT key lookup works with
`HTTPS_PROXY` and keeps its private-address protection.

Set `FASTMCP_SSRF_TRUST_PROXY=true` only when:

- This host cannot resolve the provider's name, because external DNS is only available through the proxy.
- The proxy requires a hostname and refuses a connection to a validated IP
  address.

With this setting, the proxy chooses the destination address. The MCP server can
no longer apply its own private-address block. Enable it only for a proxy that
your organization trusts. HTTPS and certificate checks remain enabled.

The server refuses to start if this setting is enabled without `HTTPS_PROXY` or
`ALL_PROXY`. It logs the name of the proxy variable, but never logs the proxy
URL because that URL may contain a password.

```bash
export HTTPS_PROXY=http://proxy.corp.example:3128
export FASTMCP_SSRF_TRUST_PROXY=true
```

Introspection follows the same rule unless
`MCP_AUTH_INTROSPECTION_ALLOW_PRIVATE=true`.

## Logging and troubleshooting

Set `MCP_REDFISH_LOG_LEVEL=DEBUG` when you need detailed troubleshooting.

The MCP Server uses these levels:

- `INFO` shows the effective transport, authentication mode, token backend,
  bind address, TLS source, Host/Origin mode, and counts of configured targets
  and required scopes.
- `DEBUG` shows stable reason codes for rejected tokens and identity-provider
  network failures.
- `WARNING` shows explicit unsafe or break-glass choices.
- `ERROR` shows configuration and startup failures. Unexpected failures include
  the exception type; `DEBUG` adds safe file, line, and function locations
  without printing the exception message.

Logs never include Bearer tokens, token claims, client secrets, passwords,
private or public key contents, required scope names, identity-provider response
bodies, or proxy URLs. Provider logs from FastMCP are sanitized before they
reach the configured handlers.

Expected client authentication failures use `DEBUG`, not `WARNING`, to prevent
an unauthenticated client from flooding normal operational logs.

## Startup failures

A configuration error is reported as a single `Configuration error: …` line
and this MCP Server exits with a non-zero status. There is no fallback parser
and no traceback. If the MCP Server fails to start for another reason, it also
exits with a non-zero status so a supervisor or Kubernetes can restart it.

## Makefile HTTP targets

`make run-sse` and `make run-streamable-http` do **not** set `MCP_HTTP_AUTH=false`. They fail closed unless you export auth env. Prefer `make run-streamable-http` with `MCP_AUTH_MODE=token` (or `MCP_HTTP_AUTH=false` only for a lab).

## Manual identity-provider checks

Automated tests use a local JWT key pair and a mocked introspection endpoint. Cloud IdPs are not a CI gate. See [MCP_AUTH_MANUAL_IDP.md](./MCP_AUTH_MANUAL_IDP.md).
