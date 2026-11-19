import json
from io import BytesIO
from django.conf import settings

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .forms import SearchJobForm
from .mcp_client import SOURCE_REGISTRY
from .models import BusinessLead, BusinessPhone, BusinessPhoneEvidence, LeadEvidence, SearchJob, SourceExecution, SuppressedPhone
from .tasks import run_search_job


def owned_job(user, job_id):
    return get_object_or_404(SearchJob, pk=job_id, owner=user)


@login_required
def search(request):
    if request.method == "POST":
        form = SearchJobForm(request.POST)
        if form.is_valid():
            active_jobs = request.user.search_jobs.filter(status__in=[SearchJob.Status.QUEUED, SearchJob.Status.RUNNING]).count()
            if active_jobs >= 3:
                form.add_error(None, "حداکثر ۳ جست‌وجو می‌تواند هم‌زمان در صف یا در حال اجرا باشد.")
                jobs = SearchJob.objects.filter(owner=request.user)[:10]
                return render(request, "leads/search.html", {"form": form, "jobs": jobs}, status=429)
            job = SearchJob.objects.create(
                owner=request.user,
                trade_name=form.cleaned_data["trade_name"],
                geographic_scope_type=form.cleaned_data["geographic_scope_type"],
                geographic_scope_name=form.cleaned_data["geographic_scope_name"],
                selected_sources=form.cleaned_data["sources"],
                max_results=form.cleaned_data["max_results"],
            )
            SourceExecution.objects.bulk_create([SourceExecution(search_job=job, source_name=source) for source in job.selected_sources])
            try:
                queued_task = run_search_job.delay(job.pk)
                job.celery_task_id = queued_task.id
                job.save(update_fields=["celery_task_id"])
            except Exception:
                job.status = SearchJob.Status.FAILED
                job.completed_at = timezone.now()
                job.error_summary = "صف Redis در دسترس نیست؛ Redis و worker را راه‌اندازی کنید و جست‌وجوی تازه‌ای ثبت کنید."
                job.total_errors = len(job.selected_sources)
                job.save(update_fields=["status", "completed_at", "error_summary", "total_errors"])
                SourceExecution.objects.filter(search_job=job).update(
                    status=SourceExecution.Status.FAILED,
                    completed_at=timezone.now(),
                    error_count=1,
                    error_details="صف Celery/Redis در دسترس نیست.",
                )
                messages.error(request, "کار ساخته شد اما Redis در دسترس نیست. راهنمای اجرا را ببینید و دوباره تلاش کنید.")
            else:
                messages.success(request, "جست‌وجو در صف قرار گرفت.")
            return redirect("job_detail", job_id=job.pk)
    else:
        form = SearchJobForm(initial={"sources": settings.ENABLED_MCP_SOURCES})
    jobs = SearchJob.objects.filter(owner=request.user)[:10]
    return render(request, "leads/search.html", {"form": form, "jobs": jobs})


@login_required
def job_detail(request, job_id):
    job = owned_job(request.user, job_id)
    queue_wait_seconds = max(0, int((timezone.now() - job.created_at).total_seconds())) if job.status == SearchJob.Status.QUEUED else 0
    resume_at = job.source_executions.filter(
        status__in=[SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN],
        cooldown_until__gt=timezone.now(),
    ).order_by("cooldown_until").values_list("cooldown_until", flat=True).first()
    # Only mobile-qualified businesses are presented as successful results.
    leads = job.leads.filter(has_mobile_phone=True)
    source = request.GET.get("source", "")
    city = request.GET.get("city", "").strip()[:120]
    verification = request.GET.get("verification", "")
    has_phone = request.GET.get("has_phone", "") == "1"
    has_website = request.GET.get("has_website", "") == "1"
    available_sources = list(job.source_executions.values_list("source_name", flat=True))
    source_phone_stats = []
    for source_name in available_sources:
        phone_evidence = BusinessPhoneEvidence.objects.filter(
            source_name=source_name, business_phone__business_lead__search_job=job,
        )
        source_phone_stats.append({
            "source": source_name,
            "businesses_with_mobile": phone_evidence.values("business_phone__business_lead_id").distinct().count(),
            "unique_mobiles": phone_evidence.values("business_phone__normalized_number").distinct().count(),
            "phone_evidence": phone_evidence.count(),
        })
    if source in available_sources:
        leads = leads.filter(source_names__icontains=source)
    if city:
        leads = leads.filter(city__icontains=city)
    if verification in BusinessLead.Verification.values:
        leads = leads.filter(verification_status=verification)
    if has_phone:
        leads = leads.filter(has_mobile_phone=True)
    if has_website:
        leads = leads.exclude(website="")
    page = Paginator(leads.prefetch_related("evidence", "business_phones"), 25).get_page(request.GET.get("page"))
    return render(request, "leads/job_detail.html", {
        "job": job,
        "queue_wait_seconds": queue_wait_seconds,
        "resume_at": resume_at,
        "page_obj": page,
        "verification_choices": BusinessLead.Verification.choices,
        "phone_status_choices": BusinessLead.PhoneStatus.choices,
        "source_catalog": SOURCE_REGISTRY,
        "available_sources": available_sources,
        "source_phone_stats": source_phone_stats,
        "summary": {
            "with_phone": job.leads.filter(has_mobile_phone=True).count(),
            "without_phone": job.leads.filter(has_mobile_phone=False).count(),
            "with_email": job.leads.filter(has_mobile_phone=True).exclude(emails=[]).count(),
            "with_website": job.leads.filter(has_mobile_phone=True).exclude(website="").count(),
            "partial_sources": job.source_executions.filter(status__in=[SourceExecution.Status.PARTIAL, SourceExecution.Status.SKIPPED, SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN]).count(),
            "successful_sources": job.source_executions.filter(status=SourceExecution.Status.COMPLETED).count(),
            "limited_sources": job.source_executions.filter(status__in=[SourceExecution.Status.RATE_LIMITED, SourceExecution.Status.LONG_COOLDOWN]).count(),
        },
        "filters": {"source": source, "city": city, "verification": verification, "has_phone": has_phone, "has_website": has_website},
    })


@login_required
@require_POST
def cancel_job(request, job_id):
    job = owned_job(request.user, job_id)
    with transaction.atomic():
        job = SearchJob.objects.select_for_update().get(pk=job.pk, owner=request.user)
        if job.status not in {SearchJob.Status.QUEUED, SearchJob.Status.RUNNING}:
            messages.info(request, "این جست‌وجو قبلاً پایان یافته است.")
            return redirect("job_detail", job_id=job.pk)
        was_running = job.status == SearchJob.Status.RUNNING
        now = timezone.now()
        SearchJob.objects.filter(
            pk=job.pk, status__in=[SearchJob.Status.QUEUED, SearchJob.Status.RUNNING]
        ).update(
            status=SearchJob.Status.CANCELLED,
            completed_at=now,
            error_summary="جست‌وجو به درخواست کاربر لغو شد؛ نتایج جمع‌آوری‌شده حفظ شده‌اند.",
        )
        SourceExecution.objects.filter(
            search_job=job,
            status__in=[SourceExecution.Status.QUEUED, SourceExecution.Status.RUNNING],
        ).update(
            status=SourceExecution.Status.CANCELLED,
            completed_at=now,
            error_details="جست‌وجو به درخواست کاربر لغو شد.",
        )
    if job.celery_task_id:
        try:
            from config.celery import app as celery_app

            celery_app.control.revoke(
                job.celery_task_id, terminate=was_running, signal="SIGTERM"
            )
        except Exception:
            pass
    messages.success(request, "درخواست لغو ثبت شد؛ نتایج به‌دست‌آمده حفظ شدند.")
    return redirect("job_detail", job_id=job.pk)


@login_required
def lead_detail(request, job_id, lead_id):
    job = owned_job(request.user, job_id)
    lead = get_object_or_404(BusinessLead, pk=lead_id, search_job=job, has_mobile_phone=True)
    return render(request, "leads/lead_detail.html", {
        "job": job, "lead": lead, "evidence": lead.evidence.all(),
        "phone_rows": lead.business_phones.prefetch_related("evidence").all(),
    })


def _json_safe_value(value):
    return value


def _export_leads(request, job):
    leads = job.leads.filter(has_mobile_phone=True).prefetch_related("business_phones__evidence")
    source = request.GET.get("source", "")
    city = request.GET.get("city", "").strip()[:120]
    category = request.GET.get("category", "").strip()[:160]
    try:
        minimum_confidence = max(0.0, min(1.0, float(request.GET.get("min_confidence", "0"))))
    except (TypeError, ValueError):
        minimum_confidence = 0.0
    if source and source in job.source_executions.values_list("source_name", flat=True):
        leads = leads.filter(source_names__icontains=source)
    if city:
        leads = leads.filter(city__icontains=city)
    if category:
        leads = leads.filter(business_category__icontains=category)
    leads = leads.filter(confidence_score__gte=minimum_confidence)
    campaign = request.GET.get("permission") == "marketing"
    suppressed = set(SuppressedPhone.objects.values_list("normalized_number", flat=True))
    if campaign:
        eligible = BusinessPhone.objects.filter(
            business_lead__search_job=job,
            permission_status=BusinessPhone.PermissionStatus.MARKETING_PERMISSION_CONFIRMED,
            permission_confirmed_at__isnull=False,
        ).exclude(normalized_number__in=suppressed).exclude(permission_evidence="").values_list("business_lead_id", flat=True)
        leads = leads.filter(pk__in=eligible)
    return leads, campaign, suppressed


def _export_phone_rows(lead, campaign, suppressed):
    rows = list(lead.business_phones.all())
    if rows:
        return [phone for phone in rows if phone.normalized_number not in suppressed
                and phone.permission_status not in {BusinessPhone.PermissionStatus.OPTED_OUT, BusinessPhone.PermissionStatus.SUPPRESSED}
                and (not campaign or (
                    phone.permission_status == BusinessPhone.PermissionStatus.MARKETING_PERMISSION_CONFIRMED
                    and bool(phone.permission_evidence.strip()) and phone.permission_confirmed_at is not None
                ))]
    if campaign:
        return []
    return [type("LegacyPhone", (), {"normalized_number": number, "permission_status": BusinessPhone.PermissionStatus.UNKNOWN})
            for number in lead.phone_numbers if number not in suppressed]


def _phone_evidence_rows(phone):
    return list(phone.evidence.all()) if isinstance(phone, BusinessPhone) else []


@login_required
def export_json(request, job_id):
    job = owned_job(request.user, job_id)
    leads, campaign, suppressed = _export_leads(request, job)
    payload = {
        "job": {"id": job.pk, "trade_name": job.trade_name, "scope_type": job.geographic_scope_type,
                "scope_name": job.geographic_scope_name, "status": job.status,
                "export_permission_filter": "marketing_permission_confirmed" if campaign else "non_suppressed"},
        "results": [{
            "name": lead.original_name,
            "phones": [phone.normalized_number for phone in _export_phone_rows(lead, campaign, suppressed)],
            "phone_details": [{"number": phone.normalized_number, "permission_status": phone.permission_status,
                               "permission_evidence": getattr(phone, "permission_evidence", ""),
                               "permission_confirmed_at": phone.permission_confirmed_at.isoformat() if getattr(phone, "permission_confirmed_at", None) else None,
                               "evidence": [{"source": item.source_name, "record_id": item.source_record_id,
                                             "source_url": item.source_url, "field_path": item.field_path,
                                             "raw_value": item.raw_value, "collected_at": item.collected_at.isoformat(),
                                             "confidence": item.confidence_score, "business_match_status": item.business_match_status}
                                            for item in _phone_evidence_rows(phone)]}
                              for phone in _export_phone_rows(lead, campaign, suppressed)],
            "address": lead.address, "city": lead.city,
            "province": lead.province, "website": lead.website, "emails": lead.emails, "social_urls": lead.social_urls,
            "national_id": lead.national_id, "business_type": lead.business_type, "phone_status": lead.phone_status,
            "confidence_score": lead.confidence_score, "category": lead.business_category,
            "latitude": lead.latitude, "longitude": lead.longitude, "sources": lead.source_names,
            "verification_status": lead.verification_status,
            "evidence": [{"source": item.source_name, "record_id": item.source_record_id, "url": item.source_url,
                          "field": item.field_name, "value": item.field_value, "collected_at": item.collected_at.isoformat()}
                         for item in lead.evidence.all() if item.field_name not in {"raw_response", "phone_numbers"}],
        } for lead in leads],
        "sources": [{
            "source": execution.source_name, "status": execution.status, "requests": execution.request_count,
            "raw_results": execution.result_count, "errors": execution.error_count,
            "message": execution.error_details, "queries": execution.query_variants,
            "areas_checked": execution.areas_checked, "checkpoint": execution.checkpoint,
            "truncated": execution.truncated,
        } for execution in job.source_executions.all()],
    }
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="leads-job-{job.pk}.json"'
    return response


def _excel_safe(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@login_required
def export_excel(request, job_id):
    job = owned_job(request.user, job_id)
    leads, campaign, suppressed = _export_leads(request, job)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "سرنخ‌ها"
    headers = ["نام کسب‌وکار", "صنف/دسته", "شهر", "استان", "نشانی", "تلفن عمومی", "ایمیل عمومی", "وب‌سایت", "شبکهٔ اجتماعی", "شناسهٔ ملی", "نوع کسب‌وکار", "منبع", "امتیاز کیفیت", "وضعیت تلفن", "وضعیت بررسی"]
    sheet.append(headers)
    for lead in leads:
        phone_rows = _export_phone_rows(lead, campaign, suppressed)
        sheet.append([_excel_safe(value) for value in [
            lead.original_name, lead.business_category, lead.city, lead.province, lead.address,
            "، ".join(phone.normalized_number for phone in phone_rows), "، ".join(lead.emails), lead.website,
            "، ".join(lead.social_urls), lead.national_id, lead.business_type,
            "، ".join(lead.source_names), lead.confidence_score, lead.get_phone_status_display(), lead.get_verification_status_display(),
        ]])
    phone_sheet = workbook.create_sheet('شواهد موبایل')
    phone_sheet.append(["Business", "E.164 mobile", "Permission status", "Source", "Source record", "Field path", "Raw value", "Confidence", "Business match", "Collected at"])
    for lead in leads:
        for phone in _export_phone_rows(lead, campaign, suppressed):
            evidence_rows = _phone_evidence_rows(phone)
            for item in evidence_rows:
                phone_sheet.append([_excel_safe(value) for value in [
                    lead.original_name, phone.normalized_number, phone.permission_status,
                    item.source_name, item.source_record_id, item.field_path, item.raw_value,
                    item.confidence_score, item.business_match_status, item.collected_at.isoformat(),
                ]])
            if not evidence_rows:
                phone_sheet.append([_excel_safe(value) for value in [lead.original_name, phone.normalized_number, phone.permission_status]])
    evidence = workbook.create_sheet("شواهد")
    evidence.append(["نام کسب‌وکار", "منبع", "شناسهٔ منبع", "پیوند", "فیلد", "مقدار", "زمان گردآوری"])
    for item in LeadEvidence.objects.filter(business_lead_id__in=leads.values_list("pk", flat=True)).exclude(
        field_name__in=["raw_response", "phone_numbers"],
    ).select_related("business_lead"):
        evidence.append([_excel_safe(value) for value in [
            item.business_lead.original_name, item.source_name, item.source_record_id, item.source_url,
            item.field_name, item.field_value, item.collected_at.isoformat(),
        ]])
    for current in workbook.worksheets:
        current.freeze_panes = "A2"
        current.auto_filter.ref = current.dimensions
        for cell in current[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="176B57")
            cell.alignment = Alignment(horizontal="right")
        for column in current.columns:
            current.column_dimensions[column[0].column_letter].width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 55)
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="leads-job-{job.pk}.xlsx"'
    return response


def health(request):
    return HttpResponse("ok", content_type="text/plain; charset=utf-8")
