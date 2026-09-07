"""Media helpers: URL resolution and the per-page Audio service.

The Audio service is created once per page/session, with a concrete ``src``,
and registered into ``page.services`` *before* the page is built/rendered.
flet binds a client-side invoke-method listener for a service when it is
added to the page — registering late/after page open (or without a ``src``)
is what caused ``Timeout waiting for invoke method listener`` errors (see the
flet 0.86.4 changelog). The instance is stored via ``services.page_store``
(a strong, per-page reference — flet drops weakly-referenced services from
the registry) rather than a module-level global: a module global is shared
by every connected browser session in the same server process, which caused
audio started on one client's page to actually play back on a different
client's page.
"""

from __future__ import annotations

import re
import urllib.parse

import flet as ft
from flet_audio import Audio

from services.page_store import get_or_create

# A local, valid silent source satisfies the service's construction contract
# without fetching quiz media on the logged-out page. It is replaced with the
# real URL whenever a question's audio player attaches.
PLACEHOLDER_SRC = "/silence.wav"


def resolve_media_url(url: str | None, base_url: str) -> str:
    if not url:
        return url
    url = url.strip()
    # Some image services pass a "wrap" URL that contains the real image in
    # the imgurl query parameter; unwrap it so the <img> can load directly.
    if re.search(r"[?&]imgurl=", url):
        direct = (
            urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("imgurl")
            or [None]
        )[0]
        if direct:
            url = direct
    if url.startswith(("http://", "https://")):
        return url
    return f"{base_url.rstrip('/')}/{url.lstrip('/')}"


def register_audio(page: ft.Page, src: str = PLACEHOLDER_SRC) -> Audio:
    """Create (once per page) and register this session's Audio service.

    Call this before the page is rendered so the web client binds the
    invoke-method handler for the audio service. Idempotent per page.
    """
    audio = get_or_create(page, "audio", lambda: Audio(src=src, volume=1.0))
    if audio not in page.services:
        page.services.append(audio)
    return audio


def ensure_audio(page: ft.Page) -> Audio:
    """Return the shared Audio service, registering it if needed."""
    return register_audio(page)


def set_audio_src(page: ft.Page, resolved_url: str) -> Audio:
    """Point the shared service at ``resolved_url`` and refresh the client."""
    audio = ensure_audio(page)
    if audio.src != resolved_url:
        audio.src = resolved_url
        audio.update()
    return audio


async def stop_audio(page: ft.Page) -> None:
    """Pause this page's audio when leaving a question (Play can resume it)."""
    audio = (page.data or {}).get("audio")
    if audio is not None:
        try:
            await audio.pause()
        except Exception:
            pass


async def reset_audio_source(page: ft.Page) -> None:
    """Stop current media and release its source without replacing the service."""
    audio = ensure_audio(page)
    try:
        await audio.pause()
    except Exception:
        pass
    audio.src = PLACEHOLDER_SRC
    audio.update()


async def play_audio_bytes(page: ft.Page, content: bytes) -> None:
    """Play nonempty generated audio through the pre-registered page service."""
    if not isinstance(content, bytes) or not content:
        raise ValueError("pronunciation audio must be nonempty bytes")
    audio = ensure_audio(page)
    audio.src = content
    audio.update()
    await audio.play()


def launch_url(url: str) -> None:
    page = ft.context.page
    page.launch_url(url)
