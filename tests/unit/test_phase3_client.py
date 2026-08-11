"""Every InstagramClient method is exercised through respx; no live Graph calls."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.config import settings
from app.instagram.client import InstagramClient
from app.instagram.schemas import InstagramCarouselItem


@pytest.mark.asyncio
async def test_all_client_methods_use_the_graph_boundary() -> None:
    base = f"{settings.instagram_graph_base_url}/{settings.ig_graph_api_version}"
    async with httpx.AsyncClient() as http_client:
        client = InstagramClient(http_client)
        with respx.mock(assert_all_called=False) as mock:
            mock.post(f"{base}/user/media").mock(
                side_effect=[
                    httpx.Response(200, json={"id": "image-container"}),
                    httpx.Response(200, json={"id": "child-1"}),
                    httpx.Response(200, json={"id": "child-2"}),
                    httpx.Response(200, json={"id": "carousel-container"}),
                    httpx.Response(200, json={"id": "reel-container"}),
                ]
            )
            mock.post(f"{base}/user/media_publish").mock(
                return_value=httpx.Response(200, json={"id": "media"})
            )
            mock.get(f"{base}/media").mock(
                return_value=httpx.Response(200, json={"id": "media", "permalink": "https://ig/p"})
            )
            mock.delete(f"{base}/media").mock(
                return_value=httpx.Response(200, json={"success": True})
            )
            mock.get(f"{base}/media/insights").mock(
                return_value=httpx.Response(200, json={"data": []})
            )
            mock.get(f"{base}/media/comments").mock(
                return_value=httpx.Response(200, json={"data": [{"id": "comment", "text": "hi"}]})
            )
            mock.post(f"{base}/media/comments").mock(
                return_value=httpx.Response(200, json={"id": "created"})
            )
            mock.post(f"{base}/comment/replies").mock(
                return_value=httpx.Response(200, json={"id": "reply"})
            )

            assert (
                await client.create_image_container(
                    instagram_user_id="user", access_token="token", image_url="https://x/image.jpg"
                )
            ).id == "image-container"
            assert (
                await client.create_carousel_container(
                    instagram_user_id="user",
                    access_token="token",
                    items=[
                        InstagramCarouselItem(media_type="image", media_url="https://x/1.jpg"),
                        InstagramCarouselItem(media_type="image", media_url="https://x/2.jpg"),
                    ],
                )
            ).id == "carousel-container"
            assert (
                await client.create_reel_container(
                    instagram_user_id="user", access_token="token", video_url="https://x/video.mp4"
                )
            ).id == "reel-container"
            assert (
                await client.publish_container(
                    instagram_user_id="user", access_token="token", container_id="container"
                )
            ).id == "media"
            assert (
                await client.get_media(access_token="token", media_id="media")
            ).permalink == "https://ig/p"
            await client.delete_media(access_token="token", media_id="media")
            assert await client.get_media_insights(access_token="token", media_id="media") == {
                "data": []
            }
            assert (await client.get_comments(access_token="token", media_id="media")).comments[
                0
            ].id == "comment"
            assert (
                await client.create_comment(access_token="token", media_id="media", text="hi")
            ).id == "created"
            assert (
                await client.reply_to_comment(access_token="token", comment_id="comment", text="hi")
            ).id == "reply"
