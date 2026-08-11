"""Shared claim-locking primitives (plan.annapost.md §7, §27).

Design decisions — see ARCHITECTURE.md §10 for the recorded rationale:

- `locked_by` scheme: hostname:pid:random-suffix, generated once per runner
  process invocation via `generate_worker_id()`. hostname:pid gives an
  operator a human-readable trace of which machine/process holds a lock; the
  random suffix guarantees uniqueness even if a pid is reused across a quick
  restart, so a new invocation can never be mistaken for the one that left a
  stale lock behind.
- Stale-lock timeout: `settings.lock_stale_after_seconds` (env config, static
  — not `global_options`). It only matters when a runner crashes mid-claim,
  it's an operational safety margin rather than a knob operators need to
  tune live, so env config is enough and avoids a DB read on every claim.
"""

import os
import socket
from uuid import uuid4


def generate_worker_id() -> str:
    """Generate a `locked_by` value unique to this runner process invocation."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
