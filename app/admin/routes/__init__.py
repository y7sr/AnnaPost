"""Admin UI routes."""

from app.admin.routes.accounts import router as accounts_router
from app.admin.routes.comments import router as comments_router
from app.admin.routes.events import router as events_router
from app.admin.routes.jobs import router as jobs_router
from app.admin.routes.metrics import router as metrics_router
from app.admin.routes.posts import router as posts_router

__all__ = [
    "accounts_router",
    "comments_router",
    "events_router",
    "jobs_router",
    "metrics_router",
    "posts_router",
]
