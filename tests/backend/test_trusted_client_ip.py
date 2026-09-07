"""Contract tests for spoof-resistant client-IP handling.

These tests deliberately exercise the public proxy and same-process Flet
relay trust domains separately.  A public proxy must never acquire authority
to set the private relay header merely by forwarding a loopback-looking hop.
"""

from __future__ import annotations

import asyncio
import unittest
from collections.abc import Iterable
from ipaddress import ip_network
from typing import Any

from starlette.requests import Request

from app.core.client_ip import (
    ORIGINAL_CLIENT_SCOPE_KEY,
    SAFE_SHARED_CLIENT_IP,
    CanonicalFletClientIpMiddleware,
    PreserveOriginalPeerMiddleware,
    canonicalize_ip,
    parse_trusted_proxy_cidrs,
    resolve_auth_request_client_ip,
    resolve_client_ip,
)
from app.core.config import Settings


def _request(
    peer: str | None,
    headers: Iterable[tuple[str, str]] = (),
    *,
    original_peer: str | None | object = ...,
) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/api/v1/auth/token",
        "raw_path": b"/api/v1/auth/token",
        "query_string": b"",
        "root_path": "",
        "server": ("quiz.test", 80),
        "client": (peer, 43123) if peer is not None else None,
        "headers": [
            (name.lower().encode("latin-1"), value.encode("latin-1"))
            for name, value in headers
        ],
    }
    if original_peer is ...:
        scope[ORIGINAL_CLIENT_SCOPE_KEY] = scope["client"]
    elif original_peer is not None:
        scope[ORIGINAL_CLIENT_SCOPE_KEY] = (original_peer, 43123)
    return Request(scope)


class CanonicalizeIpTests(unittest.TestCase):
    def test_canonicalizes_ipv4_ipv6_and_ipv4_mapped_ipv6(self) -> None:
        self.assertEqual(canonicalize_ip("198.51.100.7"), "198.51.100.7")
        self.assertEqual(canonicalize_ip("2001:0db8:0:0::1"), "2001:db8::1")
        self.assertEqual(canonicalize_ip("::ffff:192.0.2.8"), "192.0.2.8")

    def test_rejects_ports_zones_whitespace_and_non_addresses(self) -> None:
        for value in (
            "198.51.100.7:443",
            "[2001:db8::1]:443",
            "fe80::1%eth0",
            " 198.51.100.7",
            "198.51.100.7 ",
            "not-an-ip",
            "",
            None,
        ):
            with self.subTest(value=value):
                self.assertIsNone(canonicalize_ip(value))


class TrustedProxyConfigurationTests(unittest.TestCase):
    def test_parses_narrow_ipv4_and_ipv6_networks(self) -> None:
        self.assertEqual(
            parse_trusted_proxy_cidrs("10.24.0.7/32, 2001:db8:10::7/128"),
            (ip_network("10.24.0.7/32"), ip_network("2001:db8:10::7/128")),
        )

    def test_empty_configuration_trusts_nobody(self) -> None:
        self.assertEqual(parse_trusted_proxy_cidrs(""), ())

    def test_invalid_broad_and_loopback_networks_fail_closed(self) -> None:
        for value in (
            "not-a-cidr",
            "0.0.0.0/0",
            "::/0",
            "10.24.0.0/24",
            "2001:db8:10::/64",
            "127.0.0.1/32",
            "::1/128",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_trusted_proxy_cidrs(value)

    def test_settings_empty_proxy_allowlist_trusts_nobody(self) -> None:
        configured = Settings(
            _env_file=None,
            MONOREPO_AUTH_URL="http://hono-app:3003",
            TRUSTED_PROXY_CIDRS="",
        )
        self.assertEqual(configured.trusted_proxy_networks, ())

    def test_settings_accepts_only_the_two_known_auth_origins(self) -> None:
        for origin in ("http://hono-app:3003", "http://127.0.0.1:4503"):
            with self.subTest(origin=origin):
                configured = Settings(
                    _env_file=None,
                    MONOREPO_AUTH_URL=origin,
                    TRUSTED_PROXY_CIDRS="",
                )
                self.assertEqual(configured.MONOREPO_AUTH_URL, origin)

    def test_settings_reject_public_or_ambiguous_auth_origins(self) -> None:
        for origin in (
            "http://localhost:3003",
            "http://hono-app",
            "http://hono-app:4503",
            "http://hono-app:3003/",
            "http://127.0.0.1:3003",
            "http://127.0.0.2:4503",
            "http://10.24.0.7:3003",
            "http://[::1]:4503",
            "https://hono-app:3003",
            "http://auth.example.com",
            "http://8.8.8.8:3003",
            "http://169.254.169.254",
            "http://[fe80::1]",
            "http://redis:6379",
            "http://u:p@hono-app:3003",
            "http://hono-app:3003?target=public",
            "http://hono-app:3003#fragment",
        ):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                Settings(
                    _env_file=None,
                    MONOREPO_AUTH_URL=origin,
                    TRUSTED_PROXY_CIDRS="",
                )


class ResolveClientIpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trusted = parse_trusted_proxy_cidrs(
            "10.24.0.7/32,10.24.0.8/32,10.24.0.9/32,"
            "2001:db8:10::7/128,2001:db8:10::8/128"
        )

    def test_untrusted_peer_cannot_supply_forwarded_identity(self) -> None:
        self.assertEqual(
            resolve_client_ip("198.51.100.20", "203.0.113.9", self.trusted),
            "198.51.100.20",
        )

    def test_trusted_multi_hop_chain_is_walked_right_to_left(self) -> None:
        self.assertEqual(
            resolve_client_ip(
                "10.24.0.7",
                "192.0.2.44, 198.51.100.99, 10.24.0.8",
                self.trusted,
            ),
            "198.51.100.99",
        )

    def test_all_trusted_forwarded_hops_fall_back_to_socket_peer(self) -> None:
        self.assertEqual(
            resolve_client_ip("10.24.0.7", "10.24.0.8, 10.24.0.9", self.trusted),
            "10.24.0.7",
        )

    def test_malformed_or_empty_hop_discards_the_entire_header(self) -> None:
        for header in (
            "198.51.100.5, not-an-ip",
            "198.51.100.5,, 10.24.0.8",
            "198.51.100.5, 10.24.0.8:443",
        ):
            with self.subTest(header=header):
                self.assertEqual(
                    resolve_client_ip("10.24.0.7", header, self.trusted),
                    "10.24.0.7",
                )

    def test_missing_or_invalid_peer_uses_shared_safe_bucket(self) -> None:
        for peer in (None, "", "not-an-ip"):
            with self.subTest(peer=peer):
                self.assertEqual(
                    resolve_client_ip(peer, "198.51.100.5", self.trusted),
                    SAFE_SHARED_CLIENT_IP,
                )

    def test_ipv6_chain_and_mapped_peer_are_canonical(self) -> None:
        self.assertEqual(
            resolve_client_ip(
                "2001:db8:10::7",
                "2001:db8:20::9, 2001:db8:10::8",
                self.trusted,
            ),
            "2001:db8:20::9",
        )
        self.assertEqual(
            resolve_client_ip("::ffff:192.0.2.8", None, self.trusted),
            "192.0.2.8",
        )


class ResolveAuthRequestClientIpTests(unittest.TestCase):
    def setUp(self) -> None:
        self.trusted = parse_trusted_proxy_cidrs("10.24.0.7/32")

    def test_exact_loopback_peer_has_private_relay_header_authority(self) -> None:
        for peer in ("127.0.0.1", "::1"):
            with self.subTest(peer=peer):
                request = _request(
                    peer,
                    [("X-Quiz-Client-IP", "::ffff:198.51.100.23")],
                )
                self.assertEqual(
                    resolve_auth_request_client_ip(request, self.trusted),
                    "198.51.100.23",
                )

    def test_mapped_loopback_peer_does_not_gain_relay_authority(self) -> None:
        request = _request(
            "::ffff:127.0.0.1",
            [("X-Quiz-Client-IP", "198.51.100.23")],
        )
        self.assertEqual(
            resolve_auth_request_client_ip(request, self.trusted),
            "127.0.0.1",
        )

    def test_loopback_relay_header_requires_one_plain_ip_value(self) -> None:
        cases = (
            [("X-Quiz-Client-IP", "198.51.100.8, 203.0.113.8")],
            [
                ("X-Quiz-Client-IP", "198.51.100.8"),
                ("X-Quiz-Client-IP", "203.0.113.8"),
            ],
            [("X-Quiz-Client-IP", "not-an-ip")],
        )
        for headers in cases:
            with self.subTest(headers=headers):
                request = _request("127.0.0.1", headers)
                self.assertEqual(
                    resolve_auth_request_client_ip(
                        request,
                        # Simulate a future configuration bug. Loopback relay
                        # failures still cannot enter the public XFF domain.
                        (ip_network("127.0.0.1/32"),),
                    ),
                    "127.0.0.1",
                )

    def test_loopback_without_relay_metadata_never_consults_public_xff(self) -> None:
        request = _request(
            "127.0.0.1",
            [("X-Forwarded-For", "198.51.100.77")],
        )
        self.assertEqual(
            resolve_auth_request_client_ip(request, (ip_network("127.0.0.1/32"),)),
            SAFE_SHARED_CLIENT_IP,
        )

    def test_trusted_traefik_dual_spoof_cannot_gain_relay_authority(self) -> None:
        request = _request(
            "10.24.0.7",
            [
                # Attacker-supplied leftmost loopback plus the public client hop
                # appended by the trusted edge.
                ("X-Forwarded-For", "127.0.0.1, 198.51.100.71"),
                ("X-Quiz-Client-IP", "203.0.113.250"),
            ],
        )
        self.assertEqual(
            resolve_auth_request_client_ip(request, self.trusted),
            "198.51.100.71",
        )

    def test_duplicate_forwarded_headers_fall_back_to_raw_peer(self) -> None:
        request = _request(
            "10.24.0.7",
            [
                ("X-Forwarded-For", "198.51.100.8"),
                ("X-Forwarded-For", "203.0.113.8"),
            ],
        )
        self.assertEqual(
            resolve_auth_request_client_ip(request, self.trusted), "10.24.0.7"
        )

    def test_missing_preserved_peer_fails_to_shared_bucket(self) -> None:
        request = _request("198.51.100.8", original_peer=None)
        self.assertEqual(
            resolve_auth_request_client_ip(request, self.trusted),
            SAFE_SHARED_CLIENT_IP,
        )


class MiddlewareTests(unittest.TestCase):
    def test_preserve_original_peer_records_raw_socket_peer_on_a_copy(self) -> None:
        original_scope: dict[str, Any] = {
            "type": "http",
            "client": ("198.51.100.90", 4567),
            "headers": [],
        }
        captured: dict[str, Any] = {}

        async def inner(scope: dict[str, Any], receive: Any, send: Any) -> None:
            captured.update(scope)

        async def receive() -> dict[str, Any]:
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            del message

        asyncio.run(
            PreserveOriginalPeerMiddleware(inner)(original_scope, receive, send)
        )

        self.assertEqual(captured[ORIGINAL_CLIENT_SCOPE_KEY], ("198.51.100.90", 4567))
        self.assertNotIn(ORIGINAL_CLIENT_SCOPE_KEY, original_scope)

    def test_flet_websocket_rewrites_client_but_preserves_raw_peer(self) -> None:
        captured: dict[str, Any] = {}

        async def inner(scope: dict[str, Any], receive: Any, send: Any) -> None:
            captured.update(scope)

        middleware = CanonicalFletClientIpMiddleware(
            inner, parse_trusted_proxy_cidrs("10.24.0.7/32")
        )
        scope: dict[str, Any] = {
            "type": "websocket",
            "client": ("10.24.0.7", 4567),
            ORIGINAL_CLIENT_SCOPE_KEY: ("10.24.0.7", 4567),
            "headers": [(b"x-forwarded-for", b"198.51.100.90")],
        }

        async def receive() -> dict[str, Any]:
            return {"type": "websocket.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            del message

        asyncio.run(middleware(scope, receive, send))

        self.assertEqual(captured["client"], ("198.51.100.90", 4567))
        self.assertEqual(captured[ORIGINAL_CLIENT_SCOPE_KEY], ("10.24.0.7", 4567))
        self.assertEqual(scope["client"], ("10.24.0.7", 4567))


if __name__ == "__main__":
    unittest.main()
