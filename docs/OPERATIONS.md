# AnnaPost operations

## Safe live checks

`app.runners.sync` only considers published posts with `next_sync_at <= now`.
For a focused authenticated read, call `app.services.sync.sync_post` on a
known published post. It reads individual Graph insight metrics and comments,
then stores an append-only local metric snapshot.

## Instagram writes

Publishing, deleting remote media, and creating or replying to comments are
external side effects. Preflight the exact post, account, media, caption, and
job. A failed publish with a stored `instagram_container_id` must be inspected
and retried through its existing job; never create a second container blindly.

## Media insight contract

`InstagramClient.get_media_insights()` sends one request for each metric in
`app/instagram/metrics.py:GRAPH_MEDIA_INSIGHT_METRICS`, because the configured
Graph API requires `metric`. Unsupported media-type-specific metrics are kept
in `raw_metrics_json.unavailable_metrics`; authentication, permission,
rate-limit, and network failures still fail the sync.
