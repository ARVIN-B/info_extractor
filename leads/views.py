import json
from io import BytesIO
from django.conf import settings

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .forms import SearchJobForm
from .mcp_client import SOURCE_REGISTRY
from .models import BusinessLead, LeadEvidence, SearchJob, SourceExecution
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
                run_search_job.delay(job.pk)
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
    leads = job.leads.all()
    source = request.GET.get("source", "")
    city = request.GET.get("city", "").strip()[:120]
    verification = request.GET.get("verification", "")
    has_phone = request.GET.get("has_phone", "") == "1"
    has_website = request.GET.get("has_website", "") == "1"
    if source in job.selected_sources:
        leads = leads.filter(source_names__icontains=source)
    if city:
        leads = leads.filter(city__icontains=city)
    if verification in BusinessLead.Verification.values:
        leads = leads.filter(verification_status=verification)
    if has_phone:
        leads = leads.exclude(phone_numbers=[])
    if has_website:
        leads = leads.exclude(website="")
    page = Paginator(leads.prefetch_related("evidence"), 25).get_page(request.GET.get("page"))
    return render(request, "leads/job_detail.html", {
        "job": job,
        "queue_wait_seconds": queue_wait_seconds,
        "page_obj": page,
        "verification_choices": BusinessLead.Verification.choices,
        "phone_status_choices": BusinessLead.PhoneStatus.choices,
        "source_catalog": SOURCE_REGISTRY,
        "summary": {
            "with_phone": job.leads.exclude(phone_numbers=[]).count(),
            "without_phone": job.leads.filter(phone_numbers=[]).count(),
            "with_email": job.leads.exclude(emails=[]).count(),
            "with_website": job.leads.exclude(website="").count(),
            "partial_sources": job.source_executions.filter(status__in=[SourceExecution.Status.PARTIAL, SourceExecution.Status.SKIPPED]).count(),
        },
        "filters": {"source": source, "city": city, "verification": verification, "has_phone": has_phone, "has_website": has_website},
    })


@login_required
def lead_detail(request, job_id, lead_id):
    job = owned_job(request.user, job_id)
    lead = get_object_or_404(BusinessLead, pk=lead_id, search_job=job)
    return render(request, "leads/lead_detail.html", {"job": job, "lead": lead, "evidence": lead.evidence.all()})


def _json_safe_value(value):
    return value


@login_required
def export_json(request, job_id):
    job = owned_job(request.user, job_id)
    leads = job.leads.prefetch_related("evidence").all()
    payload = {
        "job": {"id": job.pk, "trade_name": job.trade_name, "scope_type": job.geographic_scope_type,
                "scope_name": job.geographic_scope_name, "status": job.status},
        "results": [{
            "name": lead.original_name, "phones": lead.phone_numbers, "address": lead.address, "city": lead.city,
            "province": lead.province, "website": lead.website, "emails": lead.emails, "social_urls": lead.social_urls,
            "national_id": lead.national_id, "business_type": lead.business_type, "phone_status": lead.phone_status,
            "confidence_score": lead.confidence_score, "category": lead.business_category,
            "latitude": lead.latitude, "longitude": lead.longitude, "sources": lead.source_names,
            "verification_status": lead.verification_status,
            "evidence": [{"source": item.source_name, "record_id": item.source_record_id, "url": item.source_url,
                          "field": item.field_name, "value": item.field_value, "collected_at": item.collected_at.isoformat()}
                         for item in lead.evidence.all()],
        } for lead in leads],
        "sources": [{
            "source": execution.source_name, "status": execution.status, "requests": execution.request_count,
            "raw_results": execution.result_count, "errors": execution.error_count,
            "message": execution.error_details, "queries": execution.query_variants,
            "areas_checked": execution.areas_checked, "truncated": execution.truncated,
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
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "سرنخ‌ها"
    headers = ["نام کسب‌وکار", "صنف/دسته", "شهر", "استان", "نشانی", "تلفن عمومی", "ایمیل عمومی", "وب‌سایت", "شبکهٔ اجتماعی", "شناسهٔ ملی", "نوع کسب‌وکار", "منبع", "امتیاز کیفیت", "وضعیت تلفن", "وضعیت بررسی"]
    sheet.append(headers)
    for lead in job.leads.all():
        sheet.append([_excel_safe(value) for value in [
            lead.original_name, lead.business_category, lead.city, lead.province, lead.address,
            "، ".join(lead.phone_numbers), "، ".join(lead.emails), lead.website,
            "، ".join(lead.social_urls), lead.national_id, lead.business_type,
            "، ".join(lead.source_names), lead.confidence_score, lead.get_phone_status_display(), lead.get_verification_status_display(),
        ]])
    evidence = workbook.create_sheet("شواهد")
    evidence.append(["نام کسب‌وکار", "منبع", "شناسهٔ منبع", "پیوند", "فیلد", "مقدار", "زمان گردآوری"])
    for item in LeadEvidence.objects.filter(business_lead__search_job=job).select_related("business_lead"):
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
