import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import BusinessLead, SearchJob, SourceExecution
from .mcp_client import SOURCE_REGISTRY
from .sources import execute_source
from .query_expansion import expand_query

logger = logging.getLogger(__name__)


def _successful_lead_count(job):
    return job.leads.filter(has_mobile_phone=True).count()


@shared_task(name="leads.purge_expired_source_payloads")
def purge_expired_source_payloads():
    from .models import LeadEvidence

    now = timezone.now()
    count = LeadEvidence.objects.filter(raw_response_expires_at__lte=now).exclude(raw_response={}).update(
        raw_response={}, raw_response_purged_at=now,
    )
    return {"purged": count}


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

    if not job.query_expansion:
        try:
            job.query_expansion = expand_query(job.trade_name)
        except Exception:
            # Expansion is an enhancement; the source pipeline always receives
            # the original query if cache/database/provider expansion fails.
            logger.exception("Query expansion failed for job %s; using original query", job_id)
            job.query_expansion = {"original_query": job.trade_name, "variants": [], "success": False}
        job.save(update_fields=["query_expansion"])

    success_count = job.source_executions.filter(status=SourceExecution.Status.COMPLETED).count()
    try:
        executions = {item.source_name: item for item in job.source_executions.all()}
        # Preserve the user's selected source order so early sources cannot consume
        # the whole result budget before later, higher-value sources run.
        ordered_sources = list(dict.fromkeys(job.selected_sources))
        ordered_sources.extend(name for name in executions if name not in ordered_sources)
        cursor = 0
        fallback_depth = {}
        while cursor < len(ordered_sources):
            source_name = ordered_sources[cursor]
            cursor += 1
            if SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.CANCELLED).exists():
                return {"status": SearchJob.Status.CANCELLED, "leads": _successful_lead_count(job)}
            execution = executions.get(source_name)
            if execution is None:
                continue
            if execution.status == SourceExecution.Status.COMPLETED:
                continue
            if execution.status == SourceExecution.Status.BUDGET_EXHAUSTED:
                continue
            if execution.status in {SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN} and execution.cooldown_until and execution.cooldown_until > timezone.now():
                continue
            execute_source(execution.source_name, job, execution)
            execution.refresh_from_db(fields=["status", "error_type", "cooldown_until"])
            if execution.status == SourceExecution.Status.COMPLETED:
                success_count += 1
            if settings.SOURCE_FALLBACK_ENABLED and execution.error_type in {"rate_limit", "long_cooldown"}:
                group = SOURCE_REGISTRY.get(source_name, {}).get("fallback_group")
                depth = fallback_depth.get(source_name, 0)
                if group and depth < settings.SOURCE_FALLBACK_MAX_DEPTH:
                    candidates = sorted(
                        (name for name, config in SOURCE_REGISTRY.items()
                         if name in settings.ENABLED_MCP_SOURCES
                         and config.get("fallback_group") == group
                         and name not in executions),
                        key=lambda name: SOURCE_REGISTRY[name].get("fallback_order", 99),
                    )
                    if candidates:
                        fallback_name = candidates[0]
                        fallback_execution = SourceExecution.objects.create(
                            search_job=job, source_name=fallback_name,
                            fallback_source=source_name,
                        )
                        executions[fallback_name] = fallback_execution
                        ordered_sources.insert(cursor, fallback_name)
                        fallback_depth[fallback_name] = depth + 1
                        execution.fallback_source = fallback_name
                        execution.save(update_fields=["fallback_source"])
            job.total_raw_results = sum(job.source_executions.values_list("result_count", flat=True))
            job.total_unique_businesses = _successful_lead_count(job)
            job.total_errors = sum(job.source_executions.values_list("error_count", flat=True))
            job.save(update_fields=["total_raw_results", "total_unique_businesses", "total_errors"])
        pending = job.source_executions.filter(status=SourceExecution.Status.QUEUED).exists()
        if pending:
            queued = SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.RUNNING).update(
                status=SearchJob.Status.QUEUED, started_at=None, completed_at=None,
            )
            if queued:
                continuation = run_search_job.apply_async(args=[job_id], countdown=0)
                SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.QUEUED).update(celery_task_id=continuation.id)
                return {"status": SearchJob.Status.QUEUED, "leads": _successful_lead_count(job), "continuing": True}
        real_failure_statuses = [SourceExecution.Status.PARTIAL, SourceExecution.Status.FAILED]
        errors = list(job.source_executions.filter(status__in=real_failure_statuses).values_list("source_name", "error_details"))
        limited_sources = job.source_executions.filter(status__in=[SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN]).count()
        job.error_summary = "\n".join(f"{source}: {message}" for source, message in errors)
        if limited_sources and not errors:
            job.error_summary = "برخی منابع محدودیت دسترسی موقت داشتند؛ نتایج منابع در دسترس جمع‌آوری شدند."
        active_cooldown = job.source_executions.filter(
            status__in=[SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN],
            cooldown_until__gt=timezone.now(),
        ).order_by("cooldown_until").first()
        if active_cooldown and not errors:
            delay = max(1, int((active_cooldown.cooldown_until - timezone.now()).total_seconds()))
            queued = SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.RUNNING).update(
                status=SearchJob.Status.QUEUED, completed_at=None,
            )
            if queued:
                continuation = run_search_job.apply_async(args=[job_id], countdown=delay)
                SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.QUEUED).update(celery_task_id=continuation.id)
                return {"status": SearchJob.Status.QUEUED, "leads": _successful_lead_count(job), "resume_in_seconds": delay}
        has_results = job.leads.filter(has_mobile_phone=True).exists()
        budget_stops = job.source_executions.filter(status=SourceExecution.Status.BUDGET_EXHAUSTED).count()
        budget_message = "\nسقف داخلی درخواست منبع به پایان رسید؛ برای ادامه باید سقف مجاز را افزایش دهید." if budget_stops else ""
        job.status = SearchJob.Status.FAILED if errors and not success_count and not has_results else (SearchJob.Status.PARTIAL if errors or budget_stops else SearchJob.Status.COMPLETED)
        job.total_unique_businesses = _successful_lead_count(job)
        job.total_raw_results = sum(job.source_executions.values_list("result_count", flat=True))
        job.total_errors = sum(job.source_executions.values_list("error_count", flat=True))
        job.completed_at = timezone.now()
        updated = SearchJob.objects.filter(pk=job_id, status=SearchJob.Status.RUNNING).update(
            status=job.status,
            completed_at=job.completed_at,
            error_summary=job.error_summary + budget_message,
            total_raw_results=job.total_raw_results,
            total_unique_businesses=job.total_unique_businesses,
            total_errors=job.total_errors,
        )
        if not updated:
            job.refresh_from_db(fields=["status"])
            return {"status": job.status, "leads": _successful_lead_count(job)}
        return {"status": job.status, "leads": job.total_unique_businesses, "errors": job.total_errors}
    except Exception:
        logger.exception("Search job %s failed", job_id)
        job.refresh_from_db()
        if job.status == SearchJob.Status.CANCELLED:
            return {"status": job.status, "leads": _successful_lead_count(job)}
        job.status = SearchJob.Status.FAILED
        job.completed_at = timezone.now()
        job.error_summary = "جست‌وجو به‌دلیل خطای داخلی متوقف شد. جزئیات فنی در گزارش سرور ثبت شده است."
        job.total_unique_businesses = _successful_lead_count(job)
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
