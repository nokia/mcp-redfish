# MCP HTTP deployment and listener security

This guide explains how the MCP Server listens for HTTP connections and how to
protect the network path. It covers bind addresses, Host/Origin checks, TLS,
reverse proxies, containers, and Kubernetes.

Authentication is a separate topic. To configure JWT or token introspection,
see [MCP_AUTH.md](./MCP_AUTH.md).

## Start here

For a local HTTP lab:

```bash
export MCP_TRANSPORT=streamable-http
# FASTMCP_HOST is not set, so the MCP Server listens on 127.0.0.1.
```

For a remote deployment:

1. Set `FASTMCP_HOST` to the required network address.
2. Set exact client-facing names in `FASTMCP_HTTP_ALLOWED_HOSTS`.
3. Provide TLS in the MCP Server, or confirm that a trusted reverse proxy or
   service mesh provides TLS.
4. Configure authentication as described in [MCP_AUTH.md](./MCP_AUTH.md).

Prefer `streamable-http` instead of the older `sse` transport. Non-loopback SSE
is refused by default because SSE has no Host/Origin protection.

## Terms used in this guide

- **Bind address:** the local network address on which this MCP Server listens.
- **Loopback:** a local-only address, normally `127.0.0.1` or `::1`.
- **Network interface:** one network connection on a machine or in a container.
- **Host header:** the server name used by an HTTP client, such as
  `mcp.example.com`.
- **Origin header:** the website that started a browser request, such as
  `https://admin.example.com`.
- **TLS / HTTPS:** encryption for data sent over the network. HTTPS is HTTP
  protected by TLS.
- **Reverse proxy / service mesh:** trusted software in front of this MCP Server
  that can provide TLS and route requests.
- **DNS rebinding:** an attack that makes a public hostname resolve to a private
  or local address.
- **Pod:** one running instance of an application in Kubernetes.
- **Service:** a stable Kubernetes network name that routes traffic to pods.
- **Ingress:** a Kubernetes component that accepts traffic and routes it to a
  Service.
- **NetworkPolicy:** a Kubernetes rule that controls which network connections
  pods may receive or create.

## Bind address (`FASTMCP_HOST`)

If `FASTMCP_HOST` is empty or not set, this MCP Server listens on `127.0.0.1`.
Only programs on the same machine can connect.

If you set `FASTMCP_HOST=0.0.0.0`, this MCP Server listens on every IPv4 network
interface and may be reachable from the network.

```bash
export FASTMCP_HOST=0.0.0.0
export FASTMCP_PORT=8000
```

The MCP Server does not guess Docker, Kubernetes, or network interface
addresses. Authentication and the bind address are independent settings.

Bracketed IPv6 loopback (`[::1]`) is accepted and normalized to `::1`.

## Host and Origin protection

Streamable HTTP checks the `Host` and `Origin` headers. These checks help stop a
malicious website or misleading DNS name from reaching the MCP Server.

Local loopback connections use automatic protection. For a non-loopback bind,
protection is strict and you must list every valid client-facing server name:

```bash
export FASTMCP_HOST=0.0.0.0
export FASTMCP_HTTP_ALLOWED_HOSTS='["mcp.example.com"]'
# Add this only when a browser application must call MCP directly:
export FASTMCP_HTTP_ALLOWED_ORIGINS='["https://admin.example.com"]'
```

Use exact names. Pattern characters such as `*`, `?`, and `[` are rejected.

Setting `FASTMCP_HTTP_HOST_ORIGIN_PROTECTION=false` disables these checks and
logs a warning. Use that setting only for isolated testing.

The `sse` transport does not have Host/Origin protection. For this reason, the
MCP Server refuses non-loopback SSE by default.

If a legacy deployment cannot move to `streamable-http` immediately, set
`MCP_ALLOW_REMOTE_SSE=true`. This is an explicit break-glass setting. The MCP
Server logs a warning every time it starts. Bearer authentication and TLS rules
still apply, but they do not add Host/Origin protection.

## TLS on the MCP Server

TLS encrypts tokens and MCP data while they travel over the network. Without
TLS, anyone who can observe that network path may be able to copy a Bearer
token.

For a non-loopback address, configure one of these options:

- Set both `MCP_TLS_CERTFILE` and `MCP_TLS_KEYFILE`. This MCP Server serves
  HTTPS.
- Set `MCP_TLS_TERMINATED=true` when a trusted reverse proxy or service mesh
  provides TLS before traffic reaches this MCP Server.

`MCP_TLS_TERMINATED=true` is only a statement from the operator. It does
**not** enable encryption. Use it only when TLS really exists in front of this
MCP Server.

| Bind address | Certificate and key | `MCP_TLS_TERMINATED` | Result |
| --- | --- | --- | --- |
| Loopback | Optional | Ignored | Starts. Cleartext loopback is allowed. |
| Non-loopback | Both readable files are set | Not required | Starts with HTTPS. |
| Non-loopback | Not set | `false` or not set | Refuses to start. |
| Non-loopback | Not set | `true` | Starts with HTTP. The operator confirms that TLS exists in front. |

When `MCP_HTTP_AUTH=false`, TLS is not required, but it is still recommended to
protect MCP data.

FastMCP may print `http://…` in its startup banner even when the MCP Server uses
TLS. The MCP Server's own startup log prints the effective `http` or `https`
scheme.

## Advanced: Kubernetes and containers

The default loopback address is useful on a laptop, but a Kubernetes Service
cannot reach a container that listens only on `127.0.0.1`. Most deployments use
`FASTMCP_HOST=0.0.0.0` and protect access with authentication, TLS, exact
allowed hostnames, and a Kubernetes NetworkPolicy.

| Goal | What to set | What to avoid |
| --- | --- | --- |
| Normal Service or Ingress | Set `FASTMCP_HOST=0.0.0.0` or `::`. Add stable client-facing names to `FASTMCP_HTTP_ALLOWED_HOSTS`. Configure MCP Server TLS or set `MCP_TLS_TERMINATED=true` when the Ingress or mesh provides TLS. | Do not store a temporary pod address in configuration. |
| Listen only on the pod's primary address | Use the Kubernetes Downward API (`fieldRef: status.podIP`) for `FASTMCP_HOST`. | Do not add automatic interface discovery to this MCP Server. |
| Pod has extra network interfaces | Prefer not to expose MCP on those networks. | Remember that `0.0.0.0` listens on every IPv4 interface in the pod. |
| Listen on one named extra interface | Resolve that interface in the container startup command, export its address as `FASTMCP_HOST`, and then start the MCP Server. | Do not store temporary network addresses in Git. |

The bind address does not decide who is allowed to connect. Use a
NetworkPolicy, MCP authentication, and TLS. Prefer a cluster-internal Service
unless public access is intentional.

`0.0.0.0` with `MCP_HTTP_AUTH=false` allows every reachable client to call the
MCP tools with the configured Redfish credentials.

## Listener environment reference

| Variable | Default | Meaning |
| --- | --- | --- |
| `FASTMCP_HOST` | `127.0.0.1` | Address on which this MCP Server listens. |
| `FASTMCP_PORT` | `8000` | HTTP port. |
| `FASTMCP_HTTP_HOST_ORIGIN_PROTECTION` | `auto` on loopback; `true` remotely | Enables Streamable HTTP Host/Origin checks. Explicit `false` warns. |
| `FASTMCP_HTTP_ALLOWED_HOSTS` | FastMCP default | Exact hostnames clients may use. Required for non-loopback Streamable HTTP. |
| `FASTMCP_HTTP_ALLOWED_ORIGINS` | FastMCP default | Exact browser origins that may call the MCP Server. |
| `MCP_ALLOW_REMOTE_SSE` | `false` | Allows SSE on a non-loopback bind as a warned break-glass choice. Prefer `streamable-http`. |
| `MCP_TLS_CERTFILE` | Not set | Path to the MCP Server certificate. Must be paired with the key. |
| `MCP_TLS_KEYFILE` | Not set | Path to the private key. Never logged. |
| `MCP_TLS_TERMINATED` | `false` | Confirms that a trusted component provides TLS in front of this MCP Server. It does not enable TLS. |

## Logging

At `INFO`, the MCP Server logs the effective transport, bind address, port,
HTTP or HTTPS scheme, TLS source, and Host/Origin protection mode. It does not
log certificate contents or private keys.

Unsafe choices such as disabled Host/Origin checks, asserted upstream TLS, or
remote SSE use `WARNING`. See the
[authentication logging guide](./MCP_AUTH.md#logging-and-troubleshooting) for
token and identity-provider diagnostics.

## Related guides

- [MCP authentication](./MCP_AUTH.md)
- [Manual identity-provider checks](./MCP_AUTH_MANUAL_IDP.md)
- [End-to-end testing](../E2E_TESTING.md)
