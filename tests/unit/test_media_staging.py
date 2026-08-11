from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

import pytest

from app.cli.media_staging import (
    MediaStagingError,
    SingleFileServer,
    quick_tunnel_url_from_output,
    require_image_file,
)


def test_single_file_server_only_serves_selected_route(tmp_path: Path) -> None:
    image = tmp_path / "image.jpg"
    image.write_bytes(b"jpeg-data")
    path, content_type = require_image_file(str(image))

    with SingleFileServer(path, content_type) as server:
        with urlopen(server.local_url) as response:  # noqa: S310
            assert response.status == 200
            assert response.headers["Content-Type"] == "image/jpeg"
            assert response.read() == b"jpeg-data"
        with pytest.raises(HTTPError) as error:
            urlopen(f"{server.origin_url}/not-the-image")  # noqa: S310
        assert error.value.code == 404


def test_require_image_file_rejects_unknown_or_missing_files(tmp_path: Path) -> None:
    with pytest.raises(MediaStagingError, match="does not exist"):
        require_image_file(str(tmp_path / "missing.jpg"))
    text_file = tmp_path / "caption.txt"
    text_file.write_text("not an image")
    with pytest.raises(MediaStagingError, match="image files"):
        require_image_file(str(text_file))


def test_quick_tunnel_url_extraction() -> None:
    assert quick_tunnel_url_from_output("INF https://warm-fog.trycloudflare.com") == (
        "https://warm-fog.trycloudflare.com"
    )
