"""Small, shared HTTPX implementation of the Instagram Graph API boundary."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings
from app.instagram.errors import (
    InstagramAuthenticationError,
    InstagramError,
    InstagramNotFoundError,
    InstagramPermissionError,
    InstagramRateLimitError,
    InstagramTransientError,
    InstagramValidationError,
)
from app.instagram.schemas import (
    InstagramCarouselItem,
    InstagramCommentsPage,
    InstagramContainer,
    InstagramCreatedComment,
    InstagramMedia,
    InstagramPublishedMedia,
    InstagramRemoteComment,
)

_client: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=settings.http_connect_timeout,
                read=settings.http_read_timeout,
                write=settings.http_write_timeout,
                pool=settings.http_pool_timeout,
            ),
            limits=httpx.Limits(max_connections=20),
            headers={"User-Agent": "AnnaPost/0.1"},
        )
    return _client


class InstagramClient:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or _shared_client()

    def _url(self, path: str) -> str:
        return f"{settings.instagram_graph_base_url.rstrip('/')}/{settings.ig_graph_api_version}/{path.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        token: str,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {"access_token": token, **(params or {})}
        try:
            response = await self._client.request(
                method,
                self._url(path),
                params=payload if method == "GET" else None,
                data={"access_token": token, **(data or {})} if method != "GET" else None,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise InstagramTransientError("Instagram network request failed") from exc
        if response.status_code >= 400:
            detail = (
                response.json().get("error", {})
                if response.headers.get("content-type", "").startswith("application/json")
                else {}
            )
            message = str(detail.get("message") or "Instagram request failed")
            code = detail.get("code")
            retry_after = response.headers.get("retry-after")
            kwargs = {
                "status_code": response.status_code,
                "retry_after_seconds": int(retry_after)
                if retry_after and retry_after.isdigit()
                else None,
            }
            if response.status_code == 429:
                raise InstagramRateLimitError(message, **kwargs)
            if response.status_code >= 500:
                raise InstagramTransientError(message, **kwargs)
            if response.status_code == 404:
                raise InstagramNotFoundError(message, **kwargs)
            if response.status_code in (401,) or code in (190,):
                raise InstagramAuthenticationError(message, **kwargs)
            if response.status_code == 403 or code in (10, 200):
                raise InstagramPermissionError(message, **kwargs)
            raise InstagramValidationError(message, **kwargs)
        try:
            return response.json()
        except ValueError as exc:
            raise InstagramError(
                "Instagram returned invalid JSON", status_code=response.status_code
            ) from exc

    async def create_image_container(
        self,
        *,
        instagram_user_id: str,
        access_token: str,
        image_url: str,
        caption: str | None = None,
    ) -> InstagramContainer:
        return InstagramContainer.model_validate(
            await self._request(
                "POST",
                f"{instagram_user_id}/media",
                token=access_token,
                data={"image_url": image_url, **({"caption": caption} if caption else {})},
            )
        )

    async def create_reel_container(
        self,
        *,
        instagram_user_id: str,
        access_token: str,
        video_url: str,
        caption: str | None = None,
        share_to_feed: bool = True,
    ) -> InstagramContainer:
        return InstagramContainer.model_validate(
            await self._request(
                "POST",
                f"{instagram_user_id}/media",
                token=access_token,
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "share_to_feed": str(share_to_feed).lower(),
                    **({"caption": caption} if caption else {}),
                },
            )
        )

    async def create_carousel_container(
        self,
        *,
        instagram_user_id: str,
        access_token: str,
        items: Sequence[InstagramCarouselItem],
        caption: str | None = None,
    ) -> InstagramContainer:
        children = []
        for item in items:
            child = await self._request(
                "POST",
                f"{instagram_user_id}/media",
                token=access_token,
                data={
                    "image_url" if item.media_type == "image" else "video_url": item.media_url,
                    "media_type": "CAROUSEL_ITEM",
                },
            )
            children.append(child["id"])
        return InstagramContainer.model_validate(
            await self._request(
                "POST",
                f"{instagram_user_id}/media",
                token=access_token,
                data={
                    "media_type": "CAROUSEL",
                    "children": ",".join(children),
                    **({"caption": caption} if caption else {}),
                },
            )
        )

    async def publish_container(
        self, *, instagram_user_id: str, access_token: str, container_id: str
    ) -> InstagramPublishedMedia:
        return InstagramPublishedMedia.model_validate(
            await self._request(
                "POST",
                f"{instagram_user_id}/media_publish",
                token=access_token,
                data={"creation_id": container_id},
            )
        )

    async def get_media(self, *, access_token: str, media_id: str) -> InstagramMedia:
        raw = await self._request(
            "GET", media_id, token=access_token, params={"fields": "id,permalink,caption,timestamp"}
        )
        return InstagramMedia(
            id=raw["id"],
            permalink=raw.get("permalink"),
            caption=raw.get("caption"),
            timestamp=datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
            if raw.get("timestamp")
            else None,
            raw=raw,
        )

    async def delete_media(self, *, access_token: str, media_id: str) -> None:
        await self._request("DELETE", media_id, token=access_token)

    async def get_media_insights(self, *, access_token: str, media_id: str) -> dict[str, Any]:
        return await self._request("GET", f"{media_id}/insights", token=access_token)

    async def get_comments(
        self, *, access_token: str, media_id: str, after: str | None = None
    ) -> InstagramCommentsPage:
        raw = await self._request(
            "GET",
            f"{media_id}/comments",
            token=access_token,
            params={
                "fields": "id,text,username,timestamp,parent,like_count",
                **({"after": after} if after else {}),
            },
        )
        comments = [
            InstagramRemoteComment(
                id=x["id"],
                text=x.get("text"),
                username=x.get("username"),
                timestamp=datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00"))
                if x.get("timestamp")
                else None,
                parent_id=(x.get("parent") or {}).get("id"),
                like_count=x.get("like_count"),
                raw=x,
            )
            for x in raw.get("data", [])
        ]
        return InstagramCommentsPage(
            comments=comments, next_cursor=(raw.get("paging") or {}).get("cursors", {}).get("after")
        )

    async def create_comment(
        self, *, access_token: str, media_id: str, text: str
    ) -> InstagramCreatedComment:
        return InstagramCreatedComment.model_validate(
            await self._request(
                "POST", f"{media_id}/comments", token=access_token, data={"message": text}
            )
        )

    async def reply_to_comment(
        self, *, access_token: str, comment_id: str, text: str
    ) -> InstagramCreatedComment:
        return InstagramCreatedComment.model_validate(
            await self._request(
                "POST", f"{comment_id}/replies", token=access_token, data={"message": text}
            )
        )
