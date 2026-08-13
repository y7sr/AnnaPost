"""Import eligible desired posts from Vend1r into AnnaPost."""

from __future__ import annotations

import asyncio
import json

from app.db.session import async_session_maker
from app.services.vend1r_bridge import synchronize_vend1r_posts


async def run() -> dict[str, int]:
    """Poll Vend1r once and persist eligible posts locally.

    This runner only synchronizes desired state. It never calls Instagram;
    publication remains the responsibility of ``runner publish``.
    """
    async with async_session_maker() as session:
        return await synchronize_vend1r_posts(session)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), sort_keys=True))
