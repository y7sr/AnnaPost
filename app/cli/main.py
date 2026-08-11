"""Thin command-line wrappers over AnnaPost services and runners."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import async_session_maker


async def _main(args: argparse.Namespace) -> None:
    if args.group == "runner":
        from app.runners import actions, publish, sync

        print(
            await {"publish": publish.run, "sync": sync.run, "actions": actions.run}[args.command]()
        )
        return
    if args.group == "posts" and args.command == "publish-file":
        if not args.confirm:
            raise SystemExit(
                "Refusing to publish. Add --confirm after reviewing the image and caption."
            )
        from app.cli.publish_file import publish_file

        result = await publish_file(
            image_path=args.image,
            caption=args.caption,
            account_id=args.account_id,
            idempotency_key=args.idempotency_key,
        )
        print(json.dumps(result, indent=2))
        if not result["ok"]:
            raise SystemExit(1)
        return
    async with async_session_maker() as session:
        if args.group == "accounts":
            from app.services.accounts import list_all_accounts

            print((await list_all_accounts(session)).model_dump_json(indent=2))
        elif args.group == "posts":
            from app.services.posts import get_post, list_all_posts

            result = (
                await get_post(session, args.id)
                if args.command == "show"
                else await list_all_posts(session)
            )
            print(result.model_dump_json(indent=2) if result else "not found")
        else:
            from app.api.routes.jobs import list_jobs

            # Avoid duplicate logic: the route's read query is the only current job read model.
            print((await list_jobs(session)).model_dump_json(indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(prog="annapost")
    groups = parser.add_subparsers(dest="group", required=True)
    groups.add_parser("accounts").add_subparsers(dest="command", required=True).add_parser("list")
    posts = groups.add_parser("posts").add_subparsers(dest="command", required=True)
    posts.add_parser("list")
    show = posts.add_parser("show")
    show.add_argument("id", type=int)
    publish_file = posts.add_parser(
        "publish-file",
        help="Publish one local image through a temporary TryCloudflare URL",
    )
    publish_file.add_argument("image", help="Path to a local image file")
    publish_file.add_argument("--caption")
    publish_file.add_argument("--account-id", type=int)
    publish_file.add_argument("--idempotency-key")
    publish_file.add_argument(
        "--confirm",
        action="store_true",
        help="Required because this creates a real Instagram post",
    )
    groups.add_parser("jobs").add_subparsers(dest="command", required=True).add_parser("list")
    runner = groups.add_parser("runner").add_subparsers(dest="command", required=True)
    for name in ("publish", "sync", "actions"):
        runner.add_parser(name)
    asyncio.run(_main(parser.parse_args()))


if __name__ == "__main__":
    main()
