"""FastAPI application entry point."""

import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.admin.routes import (
    accounts as admin_accounts,
)
from app.admin.routes import (
    comments as admin_comments,
)
from app.admin.routes import (
    events as admin_events,
)
from app.admin.routes import (
    jobs as admin_jobs,
)
from app.admin.routes import (
    metrics as admin_metrics,
)
from app.admin.routes import (
    posts as admin_posts,
)
from app.api.routes import accounts, comments, events, jobs, metrics, options, posts
from app.core.logging import setup_logging

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="AnnaPost",
    description="Standalone Instagram Publishing System",
    version="0.1.0",
)

# Routes are deliberately thin; services own state transitions and runners own
# remote reconciliation.
app.include_router(accounts.router, prefix="/api/v1", tags=["accounts"])
app.include_router(posts.router, prefix="/api/v1", tags=["posts"])
app.include_router(comments.router, prefix="/api/v1", tags=["comments"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(jobs.router, prefix="/api/v1", tags=["jobs"])
app.include_router(events.router, prefix="/api/v1", tags=["events"])
app.include_router(options.router, prefix="/api/v1", tags=["options"])

# Admin UI setup
admin_path = Path(__file__).parent / "admin"
static_dir = admin_path / "static"

# Mount admin static files
app.mount("/admin/static", StaticFiles(directory=str(static_dir)), name="admin_static")

@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    logger.debug("Health check requested")
    return {"status": "ok"}


# Admin dashboard redirect
@app.get("/admin/")
async def admin_dashboard(request: Request):
    """Redirect to accounts page."""
    return RedirectResponse(url="/admin/accounts/")


# Include admin routers under /admin prefix
app.include_router(admin_accounts.router, prefix="/admin/accounts")
app.include_router(admin_posts.router, prefix="/admin/posts")
app.include_router(admin_jobs.router, prefix="/admin/jobs")
app.include_router(admin_events.router, prefix="/admin/events")
app.include_router(admin_metrics.router, prefix="/admin/metrics")
app.include_router(admin_comments.router, prefix="/admin/comments")


# For running with: python -m app.main
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True, host="0.0.0.0", port=8000)
