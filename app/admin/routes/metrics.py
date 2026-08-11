"""Admin routes for Instagram post metrics."""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.template_utils import render_template
from app.db.models.metrics import InstagramPostMetric
from app.db.models.post import InstagramPost
from app.db.session import get_db
from app.schemas.metrics import InstagramPostMetricResponse

router = APIRouter()


@router.get("/")
async def list_metrics_page(
    request: Request,
    post_id: int | None = None,
    session: AsyncSession = Depends(get_db),
):
    """Render metrics list page."""
    if post_id:
        result = await session.execute(
            select(InstagramPostMetric)
            .where(InstagramPostMetric.post_id == post_id)
            .order_by(InstagramPostMetric.captured_at.desc())
            .limit(100)
        )
    else:
        result = await session.execute(
            select(InstagramPostMetric).order_by(InstagramPostMetric.captured_at.desc()).limit(100)
        )

    metrics = result.scalars().all()
    metric_responses = [InstagramPostMetricResponse.model_validate(metric) for metric in metrics]

    return render_template(
        "metrics.html",
        request=request,
        metrics=metric_responses,
        count=len(metric_responses),
        post_id_filter=post_id,
        showing_all=post_id is None,
    )


@router.get("/{metric_id}/")
async def get_metric_page(
    request: Request,
    metric_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render metric detail page."""
    metric = await session.get(InstagramPostMetric, metric_id)
    if metric is None:
        raise HTTPException(status_code=404, detail="Metric not found")

    return render_template(
        "metric_detail.html",
        request=request,
        metric=InstagramPostMetricResponse.model_validate(metric),
    )


@router.get("/post/{post_id}/")
async def get_post_metrics_page(
    request: Request,
    post_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render metrics for a specific post."""
    post = await session.get(InstagramPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")

    result = await session.execute(
        select(InstagramPostMetric)
        .where(InstagramPostMetric.post_id == post_id)
        .order_by(InstagramPostMetric.captured_at.desc())
    )
    metrics = result.scalars().all()
    metric_responses = [InstagramPostMetricResponse.model_validate(metric) for metric in metrics]
    chronological_metrics = list(reversed(metric_responses))
    max_views = max((metric.views or 0 for metric in chronological_metrics), default=1) or 1
    max_likes = max((metric.likes or 0 for metric in chronological_metrics), default=1) or 1
    chart_points = [
        {
            "x": index * 800 / max(len(chronological_metrics) - 1, 1),
            "views_y": 200 - (metric.views or 0) * 200 / max_views,
            "likes_y": 200 - (metric.likes or 0) * 200 / max_likes,
            "views_known": metric.views is not None,
            "likes_known": metric.likes is not None,
        }
        for index, metric in enumerate(chronological_metrics)
    ]

    return render_template(
        "post_metrics.html",
        request=request,
        post=post,
        metrics=metric_responses,
        count=len(metric_responses),
        chart_points=chart_points,
    )
