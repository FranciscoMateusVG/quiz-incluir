"""Trusted client-IP resolution for the public Flet and auth relay paths.

There are deliberately two trust domains:

* ``TRUSTED_PROXY_CIDRS`` authorizes parsing the public proxy's
  ``X-Forwarded-For`` chain.
* The dedicated ``X-Quiz-Client-IP`` relay header is accepted only from the
  same-process loopback client. Proxy trust never grants relay-header trust.

The application must run Uvicorn with proxy-header rewriting disabled. This
module must see the original socket peer so it can apply the configured trust
policy itself, once.
"""

from __future__ import annotations

from collections.abc import Iterable
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_address,
    ip_network,
)
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send


IpAddress = IPv4Address | IPv6Address
IpNetwork = IPv4Network | IPv6Network

ORIGINAL_CLIENT_SCOPE_KEY = "quiz.original_client"
INTERNAL_CLIENT_IP_HEADER = "x-quiz-client-ip"
SAFE_SHARED_CLIENT_IP = "127.0.0.1"
_RELAY_PEERS = {IPv4Address("127.0.0.1"), IPv6Address("::1")}


def canonicalize_ip(value: str | None) -> str | None:
    """Return a canonical IP string, rejecting ports, zones and non-IP data."""

    if not value or value != value.strip() or "%" in value:
        return None
    try:
        parsed = ip_address(value)
    except ValueError:
        return None
    if isinstance(parsed, IPv6Address) and parsed.ipv4_mapped is not None:
        return str(parsed.ipv4_mapped)
    return str(parsed)


def parse_trusted_proxy_cidrs(value: str | Iterable[str]) -> tuple[IpNetwork, ...]:
    """Parse exact public-proxy host routes; broad/loopback trust is invalid."""

    raw_values = value.split(",") if isinstance(value, str) else list(value)
    networks: list[IpNetwork] = []
    for raw in raw_values:
        item = raw.strip()
        if not item:
            continue
        try:
            network = ip_network(item, strict=False)
        except ValueError as exc:
            raise ValueError(f"Invalid trusted proxy CIDR: {item}") from exc
        if network.prefixlen != network.max_prefixlen:
            raise ValueError("Trusted proxies must be exact /32 or /128 host routes")
        if network.network_address.is_loopback:
            raise ValueError("Loopback cannot be configured as a public trusted proxy")
        networks.append(network)
    return tuple(networks)


def _is_trusted(address: IpAddress, networks: Iterable[IpNetwork]) -> bool:
    return any(
        address.version == network.version and address in network
        for network in networks
    )


def _parse_ip(value: str | None) -> IpAddress | None:
    canonical = canonicalize_ip(value)
    return ip_address(canonical) if canonical is not None else None


def _parse_exact_ip(value: str | None) -> IpAddress | None:
    """Parse without mapped-address canonicalization for trust decisions."""

    if not value or value != value.strip() or "%" in value:
        return None
    try:
        return ip_address(value)
    except ValueError:
        return None


def resolve_client_ip(
    peer_ip: str | None,
    x_forwarded_for: str | None,
    trusted_proxy_cidrs: Iterable[IpNetwork],
) -> str:
    """Resolve one spoof-resistant IP, falling back to a shared safe bucket.

    Forwarded hops are considered only when the immediate socket peer is a
    configured proxy. The entire chain must parse. It is then walked from the
    trusted edge inward, returning the nearest untrusted hop.
    """

    peer = _parse_ip(peer_ip)
    if peer is None:
        return SAFE_SHARED_CLIENT_IP
    peer_value = str(peer)

    if not x_forwarded_for or not _is_trusted(peer, trusted_proxy_cidrs):
        return peer_value

    raw_hops = x_forwarded_for.split(",")
    if not raw_hops or any(not raw.strip() for raw in raw_hops):
        return peer_value

    hops: list[IpAddress] = []
    for raw in raw_hops:
        hop = _parse_ip(raw.strip())
        if hop is None:
            return peer_value
        hops.append(hop)

    for hop in reversed(hops):
        if not _is_trusted(hop, trusted_proxy_cidrs):
            return str(hop)
    return peer_value


def _original_peer(scope: Scope) -> tuple[str, int] | None:
    peer = scope.get(ORIGINAL_CLIENT_SCOPE_KEY)
    if not isinstance(peer, (tuple, list)) or len(peer) != 2:
        return None
    host, port = peer
    if not isinstance(host, str) or not isinstance(port, int):
        return None
    return host, port


def _single_scope_header(scope: Scope, name: bytes) -> str | None:
    values = [value for key, value in scope.get("headers", []) if key.lower() == name]
    if len(values) != 1:
        return None
    try:
        return values[0].decode("latin-1")
    except UnicodeDecodeError:
        return None


def resolve_auth_request_client_ip(
    request: Request, trusted_proxy_cidrs: Iterable[IpNetwork]
) -> str:
    """Resolve the Hono limiter key for either Flet relay or public API use."""

    original_peer = _original_peer(request.scope)
    peer_ip = original_peer[0] if original_peer is not None else None
    # Relay authority is decided from the exact preserved representation.
    # In particular, ::ffff:127.0.0.1 is not one of the two authorized peers.
    parsed_peer = _parse_exact_ip(peer_ip)

    if parsed_peer in _RELAY_PEERS:
        relay_values = request.headers.getlist(INTERNAL_CLIENT_IP_HEADER)
        if len(relay_values) == 1:
            relay_value = relay_values[0]
            if "," not in relay_value:
                canonical_relay = canonicalize_ip(relay_value)
                if canonical_relay is not None:
                    return canonical_relay
        # Loopback belongs exclusively to the same-process relay trust domain.
        # Missing/malformed relay metadata must never fall through to public
        # XFF interpretation, even under a future configuration mistake.
        return SAFE_SHARED_CLIENT_IP

    forwarded_values = request.headers.getlist("x-forwarded-for")
    forwarded = forwarded_values[0] if len(forwarded_values) == 1 else None
    return resolve_client_ip(peer_ip, forwarded, trusted_proxy_cidrs)


class PreserveOriginalPeerMiddleware:
    """Record the socket peer before any application-owned scope rewrite."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"}:
            scope = dict(scope)
            scope[ORIGINAL_CLIENT_SCOPE_KEY] = scope.get("client")
        await self.app(scope, receive, send)


class CanonicalFletClientIpMiddleware:
    """Expose a canonical public client IP through Flet ``Page.client_ip``.

    Flet 0.86.5 copies ``websocket.client.host`` into ``Page.client_ip`` before
    invoking ``main(page)``. Rewriting only the mounted Flet websocket scope
    gives the frontend server-owned metadata without reinterpreting API calls.
    """

    def __init__(self, app: ASGIApp, trusted_proxy_cidrs: Iterable[IpNetwork]) -> None:
        self.app = app
        self.trusted_proxy_cidrs = tuple(trusted_proxy_cidrs)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            original_peer = _original_peer(scope)
            peer_ip = original_peer[0] if original_peer is not None else None
            forwarded = _single_scope_header(scope, b"x-forwarded-for")
            canonical = resolve_client_ip(peer_ip, forwarded, self.trusted_proxy_cidrs)
            scope = dict(scope)
            port = original_peer[1] if original_peer is not None else 0
            scope["client"] = (canonical, port)
        await self.app(scope, receive, send)
