import logging
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from .models import JobContact, SearchJob, SourceExecution
from .sources import execute_source
from .web_search import run_web_lane
from .query_expansion import expand_query

logger = logging.getLogger(__name__)


@shared_task(name="leads.purge_expired_source_payloads")
def purge_expired_source_payloads():
    from .models import LeadEvidence

    now = timezone.now()
    count = LeadEvidence.objects.filter(raw_response_expires_at__lte=now).exclude(raw_response={}).update(
        raw_response={}, raw_response_purged_at=now,
    )
    return {"purged": count}


@shared_task(bind=True, name="leads.run_search_job", acks_late=True, reject_on_worker_lost=True, time_limit=1800, soft_time_limit=1740)
def run_search_job(self, job_id):
    started_at = timezone.now()
    claimed = SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.QUEUED).update(
        status=SearchJob.Status.RUNNING, started_at=started_at,
    )
    if not claimed:
        status = SearchJob.objects.filter(pk=job_id).values_list("status", flat=True).first()
        return {"status": status or "missing"}
    job = SearchJob.objects.get(pk=job_id)
    if not job.query_expansion:
        try:
            job.query_expansion = expand_query(job.trade_name)
        except Exception:
            logger.exception("Query expansion failed for job %s; using original query", job_id)
            job.query_expansion = {"original_query": job.trade_name, "variants": [], "success": False}
        job.save(update_fields=["query_expansion"])

    executions = {item.source_name: item for item in job.source_executions.all()}
    for source in ("neshan", "balad", "emalls", "web"):
        if source not in executions:
            executions[source] = SourceExecution.objects.create(search_job=job, source_name=source)

    def target_met():
        return JobContact.objects.filter(search_job_id=job_id).count() >= job.requested_phone_count

    def run_lane(source_name):
        execution = executions[source_name]
        while True:
            job_status = SearchJob.objects.filter(pk=job_id).values_list("status", flat=True).first()
            execution.refresh_from_db()
            if job_status == SearchJob.Status.CANCELLED:
                return
            if target_met():
                if execution.status in {SourceExecution.Status.QUEUED, SourceExecution.Status.RUNNING}:
                    execution.status = SourceExecution.Status.SKIPPED
                    execution.error_details = "هدف شماره‌های یکتا پیش از شروع این مسیر تکمیل شد."
                    execution.completed_at = timezone.now()
                    execution.save(update_fields=["status", "error_details", "completed_at"])
                return
            if execution.status in {SourceExecution.Status.COMPLETED, SourceExecution.Status.FAILED,
                                    SourceExecution.Status.PARTIAL, SourceExecution.Status.SKIPPED,
                                    SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN,
                                    SourceExecution.Status.BUDGET_EXHAUSTED, SourceExecution.Status.CANCELLED}:
                return
            if source_name == "web":
                run_web_lane(job, execution)
            else:
                execute_source(source_name, job, execution)
            execution.refresh_from_db(fields=["status"])
            if execution.status != SourceExecution.Status.QUEUED:
                return

    try:
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix=f"job-{job_id}") as pool:
            futures = {pool.submit(run_lane, name): name for name in ("neshan", "balad", "emalls", "web")}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    source_name = futures[future]
                    logger.exception("Search lane %s failed unexpectedly for job %s", source_name, job_id)
                    execution = executions[source_name]
                    execution.status = SourceExecution.Status.FAILED
                    execution.error_type = "lane_error"
                    execution.error_count = max(1, execution.error_count)
                    execution.error_details = "Lane stopped after an internal error; check server logs."
                    execution.completed_at = timezone.now()
                    execution.save(update_fields=["status", "error_type", "error_count", "error_details", "completed_at"])
        job.refresh_from_db()
        if job.status == SearchJob.Status.CANCELLED:
            return {"status": job.status, "phones": JobContact.objects.filter(search_job=job).count()}
        count = JobContact.objects.filter(search_job=job).count()
        job.total_unique_businesses = count
        job.total_raw_results = sum(job.source_executions.values_list("result_count", flat=True))
        job.total_errors = sum(job.source_executions.values_list("error_count", flat=True))
        errors = list(job.source_executions.filter(status__in=[SourceExecution.Status.PARTIAL, SourceExecution.Status.FAILED]).values_list("source_name", "error_details"))
        limited = job.source_executions.filter(status__in=[SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN]).exists()
        budget_stops = job.source_executions.filter(status=SourceExecution.Status.BUDGET_EXHAUSTED).count()
        successful_lanes = job.source_executions.filter(status__in=[SourceExecution.Status.COMPLETED, SourceExecution.Status.SKIPPED]).count()
        job.error_summary = "\n".join(f"{name}: {message}" for name, message in errors)
        if limited and not errors:
            job.error_summary = "برخی منابع محدودیت دسترسی موقت داشتند؛ نتایج منابع در دسترس حفظ شدند."
        if budget_stops and not errors and not limited:
            job.error_summary = "سقف فراخوانی MCP به پایان رسید؛ تعداد واقعی از هدف کمتر مانده است."
        if errors or limited or budget_stops:
            job.status = SearchJob.Status.PARTIAL if count or successful_lanes else SearchJob.Status.FAILED
        else:
            job.status = SearchJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "error_summary", "total_unique_businesses", "total_raw_results", "total_errors"])
        return {"status": job.status, "phones": count, "requested": job.requested_phone_count, "errors": job.total_errors}
    except Exception:
        logger.exception("Search job %s failed", job_id)
        job.refresh_from_db()
        if job.status == SearchJob.Status.CANCELLED:
            return {"status": job.status, "phones": JobContact.objects.filter(search_job=job).count()}
        job.status = SearchJob.Status.FAILED
        job.completed_at = timezone.now()
        job.error_summary = "جست‌وجو به‌دلیل خطای داخلی متوقف شد. جزئیات فنی در گزارش سرور ثبت شده است."
        job.total_unique_businesses = JobContact.objects.filter(search_job=job).count()
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
        queued_task = run_search_job.delay(job_id)
        SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.QUEUED).update(
            celery_task_id=queued_task.id
        )
    return {"requeued": len(stale_ids)}
