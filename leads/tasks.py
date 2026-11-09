import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import BusinessLead, SearchJob, SourceExecution
from .sources import execute_source

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="leads.run_search_job", acks_late=True, reject_on_worker_lost=True, time_limit=900, soft_time_limit=840)
def run_search_job(self, job_id):
    started_at = timezone.now()
    claimed = SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.QUEUED).update(
        status=SearchJob.Status.RUNNING, started_at=started_at,
    )
    if not claimed:
        status = SearchJob.objects.filter(pk=job_id).values_list("status", flat=True).first()
        return {"status": status or "missing"}
    job = SearchJob.objects.get(pk=job_id)

    success_count = job.source_executions.filter(status=SourceExecution.Status.COMPLETED).count()
    try:
        for execution in job.source_executions.all():
            if execution.status == SourceExecution.Status.COMPLETED:
                continue
            execute_source(execution.source_name, job, execution)
            execution.refresh_from_db(fields=["status"])
            if execution.status == SourceExecution.Status.COMPLETED:
                success_count += 1
            job.total_raw_results = sum(job.source_executions.values_list("result_count", flat=True))
            job.total_unique_businesses = job.leads.count()
            job.total_errors = job.source_executions.filter(status=SourceExecution.Status.FAILED).count()
            job.save(update_fields=["total_raw_results", "total_unique_businesses", "total_errors"])
        errors = list(job.source_executions.filter(status=SourceExecution.Status.FAILED).values_list("source_name", "error_details"))
        job.error_summary = "\n".join(f"{source}: {message}" for source, message in errors)
        has_results = job.leads.exists()
        job.status = SearchJob.Status.FAILED if not success_count and not has_results else (SearchJob.Status.PARTIAL if errors else SearchJob.Status.COMPLETED)
        job.total_unique_businesses = job.leads.count()
        job.total_raw_results = sum(job.source_executions.values_list("result_count", flat=True))
        job.total_errors = len(errors)
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "error_summary", "total_raw_results", "total_unique_businesses", "total_errors"])
        return {"status": job.status, "leads": job.total_unique_businesses, "errors": job.total_errors}
    except Exception:
        logger.exception("Search job %s failed", job_id)
        job.refresh_from_db()
        job.status = SearchJob.Status.FAILED
        job.completed_at = timezone.now()
        job.error_summary = "جست‌وجو به‌دلیل خطای داخلی متوقف شد. جزئیات فنی در گزارش سرور ثبت شده است."
        job.total_unique_businesses = job.leads.count()
        job.save(update_fields=["status", "completed_at", "error_summary", "total_unique_businesses"])
        raise


@shared_task(name="leads.recover_stale_search_jobs")
def recover_stale_search_jobs():
    """Requeue jobs abandoned by a killed worker after their hard task-time limit."""
    cutoff = timezone.now() - timedelta(minutes=20)
    stale_ids = list(SearchJob.objects.filter(status=SearchJob.Status.RUNNING, started_at__lt=cutoff).values_list("pk", flat=True))
    for job_id in stale_ids:
        with transaction.atomic():
            job = SearchJob.objects.select_for_update().filter(pk=job_id, status=SearchJob.Status.RUNNING, started_at__lt=cutoff).first()
            if not job:
                continue
            job.status = SearchJob.Status.QUEUED
            job.started_at = None
            job.error_summary = "Worker interrupted; job was requeued automatically."
            job.save(update_fields=["status", "started_at", "error_summary"])
            job.source_executions.filter(status__in=[SourceExecution.Status.RUNNING, SourceExecution.Status.FAILED]).update(
                status=SourceExecution.Status.QUEUED, started_at=None, completed_at=None,
            )
        run_search_job.delay(job_id)
    return {"requeued": len(stale_ids)}
