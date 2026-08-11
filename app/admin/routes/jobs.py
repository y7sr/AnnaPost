"""Admin routes for Instagram jobs."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import status as http_status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin.template_utils import render_template
from app.db.models.job import JobStatus, JobType
from app.db.session import get_db
from app.services.jobs import cancel_job, get_job_status, list_all_jobs, retry_job

router = APIRouter()


@router.get("/")
async def list_jobs_page(
    request: Request,
    job_type: str | None = None,
    status: str | None = None,
    session: AsyncSession = Depends(get_db),
):
    """Render jobs list page."""
    try:
        job_type_value = JobType(job_type) if job_type and job_type != "all" else None
    except ValueError:
        job_type_value = None
    try:
        status_value = JobStatus(status) if status and status != "all" else None
    except ValueError:
        status_value = None

    jobs_list = await list_all_jobs(
        session, job_type=job_type_value, status=status_value, limit=100
    )
    return render_template(
        "jobs.html",
        request=request,
        jobs=jobs_list.jobs,
        count=jobs_list.count,
        job_type_filter=job_type or "all",
        status_filter=status or "all",
        job_type_values=[jt.value for jt in JobType],
        status_values=[value.value for value in JobStatus],
    )


@router.get("/{job_id}/")
async def get_job_page(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Render job detail page."""
    job = await get_job_status(session, job_id)
    if job is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Job not found")
    return render_template("job_detail.html", request=request, job=job)


@router.post("/{job_id}/retry/")
async def retry_job_page(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Retry a failed job through its atomic service command."""
    if not await retry_job(session, job_id):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Only failed jobs can be retried",
        )
    return RedirectResponse(url="/admin/jobs/", status_code=303)


@router.post("/{job_id}/cancel/")
async def cancel_job_page(
    request: Request,
    job_id: int,
    session: AsyncSession = Depends(get_db),
):
    """Cancel pending work before a runner claims it."""
    if not await cancel_job(session, job_id):
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="Only pending jobs can be canceled",
        )
    return RedirectResponse(url="/admin/jobs/", status_code=303)
