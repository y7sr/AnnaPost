"""Reconciliation policy contract for Phase 3 implementation.

The database is desired state/history and Instagram is observed external state.
Runners implement these rules; API routes only express desired state and never
perform reconciliation directly.

Rules:

* ``soft_deleted=True`` on a published post requires a ``delete_post`` job.
  A remote ``not found`` satisfies that desired deletion and the post becomes
  ``deleted`` locally.
* A locally published post missing remotely is a discrepancy: record an event
  and retain its local publication history. Do not silently re-publish it.
  Operator or a later explicit policy decides whether it is marked deleted.
* Remote comments are upserted by ``instagram_comment_id``; queued outgoing
  comments/replies are sent only by their jobs.
* Only transient Instagram failures receive a delayed retry. Authentication,
  permission, and validation failures are terminal until a human changes the
  account/configuration/content.

Caption policy:

``caption`` is the locally requested value. ``remote_caption_last_known`` and
``caption_sync_status`` (``in_sync | pending | unsupported | failed``) are the
future persistence contract for supported post-publication edits. If Instagram
does not support an edit, retain the local requested caption, mark it
``unsupported``, and write an event. Never imply the remote caption changed.
"""
