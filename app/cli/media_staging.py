"""Ephemeral, least-privilege media hosting for manual CLI publication."""

from __future__ import annotations

import asyncio
import mimetypes
import re
import secrets
import threading
from contextlib import AbstractContextManager
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

import httpx


class MediaStagingError(RuntimeError):
    """Raised when a local file cannot be safely exposed for publication."""


_QUICK_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)


def require_image_file(path_value: str) -> tuple[Path, str]:
    """Resolve one regular image file and determine its HTTP content type."""
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise MediaStagingError(f"Image file does not exist or is not a regular file: {path}")
    content_type, _ = mimetypes.guess_type(path.name)
    if not content_type or not content_type.startswith("image/"):
        raise MediaStagingError("publish-file currently accepts image files with a known MIME type")
    return path, content_type


class SingleFileServer(AbstractContextManager["SingleFileServer"]):
    """Serve one image at one unguessable route, bound to loopback only."""

    def __init__(self, path: Path, content_type: str) -> None:
        self.path = path
        self.content_type = content_type
        # Do not put the original filename into the URL: spaces and non-ASCII
        # characters are needlessly fragile when Instagram later fetches it.
        # Meta's media fetcher inspects both the response headers and the URL.
        # Keep the unguessable route, but retain a MIME-matched suffix so a
        # valid JPEG is not rejected as an untyped ``/media`` resource.
        suffix = mimetypes.guess_extension(content_type) or ""
        self.route = f"/{secrets.token_urlsafe(24)}/media{suffix}"
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def origin_url(self) -> str:
        if self._server is None:
            raise RuntimeError("Single-file server is not running")
        return f"http://127.0.0.1:{self._server.server_port}"

    @property
    def local_url(self) -> str:
        return f"{self.origin_url}{self.route}"

    def __enter__(self) -> SingleFileServer:
        expected_route, source_path, content_type = self.route, self.path, self.content_type

        class RequestHandler(BaseHTTPRequestHandler):
            server_version = "AnnaPostMedia/1"
            sys_version = ""
            allowed_methods: ClassVar[set[str]] = {"GET", "HEAD"}

            def do_GET(self) -> None:  # noqa: N802
                self._send_file(include_body=True)

            def do_HEAD(self) -> None:  # noqa: N802
                self._send_file(include_body=False)

            def _send_file(self, *, include_body: bool) -> None:
                if self.command not in self.allowed_methods or self.path != expected_route:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                try:
                    size = source_path.stat().st_size
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(size))
                    self.send_header("Cache-Control", "public, max-age=300")
                    self.end_headers()
                    if include_body:
                        with source_path.open("rb") as image:
                            while chunk := image.read(64 * 1024):
                                self.wfile.write(chunk)
                except OSError:
                    self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), RequestHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *_exception: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)


class QuickTunnel:
    """Own one ``cloudflared`` Quick Tunnel and expose its public URL."""

    def __init__(self, origin_url: str, *, startup_timeout_seconds: float = 30.0) -> None:
        self.origin_url = origin_url
        self.startup_timeout_seconds = startup_timeout_seconds
        self.process: asyncio.subprocess.Process | None = None
        self.public_origin: str | None = None

    async def start(self) -> str:
        self.process = await asyncio.create_subprocess_exec(
            "cloudflared",
            "tunnel",
            "--url",
            self.origin_url,
            "--no-autoupdate",
            "--loglevel",
            # cloudflared announces the Quick Tunnel URL at info level.  Keep
            # that line available to the URL parser while capturing it rather
            # than forwarding it to the terminal.
            "info",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert self.process.stdout is not None
        try:
            async with asyncio.timeout(self.startup_timeout_seconds):
                while line := await self.process.stdout.readline():
                    match = _QUICK_TUNNEL_URL.search(line.decode(errors="replace"))
                    if match:
                        self.public_origin = match.group(0)
                        await self._wait_until_reachable(self.public_origin)
                        return self.public_origin
                    if self.process.returncode is not None:
                        break
        except TimeoutError as exc:
            raise MediaStagingError("Timed out waiting for the TryCloudflare public URL") from exc
        await self.stop()
        raise MediaStagingError("cloudflared exited before creating a TryCloudflare tunnel")

    async def _wait_until_reachable(self, public_origin: str) -> None:
        """Wait for DNS and the Cloudflare edge to serve the new tunnel."""
        deadline = asyncio.get_running_loop().time() + self.startup_timeout_seconds
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            while asyncio.get_running_loop().time() < deadline:
                try:
                    # The single-file server deliberately returns 404 at its
                    # root; any non-5xx HTTP response proves that the public
                    # hostname has propagated and reaches the local origin.
                    response = await client.get(public_origin)
                    if response.status_code < 500:
                        return
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.5)
        await self.stop()
        raise MediaStagingError("TryCloudflare public URL did not become reachable")

    async def stop(self) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        self.process.terminate()
        try:
            await asyncio.wait_for(self.process.wait(), timeout=10)
        except TimeoutError:
            self.process.kill()
            await self.process.wait()


def quick_tunnel_url_from_output(output: str) -> str | None:
    """Extract a Quick Tunnel URL from cloudflared output for focused tests."""
    match = _QUICK_TUNNEL_URL.search(output)
    return match.group(0) if match else None
