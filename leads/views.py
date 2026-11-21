import json
import time
from io import BytesIO
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import connections, transaction
from django.db.utils import OperationalError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .forms import SearchJobForm
from .models import JobContact, SearchJob, SourceExecution
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
                selected_sources=["neshan", "balad", "emalls", "web"],
                max_results=form.cleaned_data["requested_phone_count"],
                requested_phone_count=form.cleaned_data["requested_phone_count"],
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
        form = SearchJobForm()
    jobs = SearchJob.objects.filter(owner=request.user)[:10]
    return render(request, "leads/search.html", {"form": form, "jobs": jobs})


@login_required
def job_detail(request, job_id):
    job = owned_job(request.user, job_id)
    queue_wait_seconds = max(0, int((timezone.now() - job.created_at).total_seconds())) if job.status == SearchJob.Status.QUEUED else 0
    contacts = job.contacts.all()
    source = request.GET.get("source", "")
    if source in {"neshan", "balad", "emalls", "web"}:
        contacts = contacts.filter(source_name=source)
    page = Paginator(contacts, 50).get_page(request.GET.get("page"))
    source_labels = {"neshan": "نشان", "balad": "بلد", "emalls": "ایمالز", "web": "وب"}
    executions = job.source_executions.filter(source_name__in=["neshan", "balad", "emalls", "web"])
    lane_stats = [{
        "source": item.source_name,
        "label": source_labels.get(item.source_name, item.source_name),
        "status": item.status,
        "status_label": item.get_status_display(),
        "count": job.contacts.filter(source_name=item.source_name).count(),
        "requests": item.request_count,
        "errors": item.error_count,
        "message": item.error_details,
    } for item in executions]
    return render(request, "leads/job_detail.html", {
        "job": job,
        "queue_wait_seconds": queue_wait_seconds,
        "page_obj": page,
        "lane_stats": lane_stats,
        "available_sources": ["neshan", "balad", "emalls", "web"],
        "filters": {"source": source},
        "found_count": job.contacts.count(),
        "progress_percent": min(100, int(job.contacts.count() * 100 / max(1, job.requested_phone_count))),
    })


@login_required
@require_POST
def cancel_job(request, job_id):
    job = owned_job(request.user, job_id)
    was_running = job.status == SearchJob.Status.RUNNING
    cancelled = False
    for attempt in range(4):
        try:
            with transaction.atomic():
                now = timezone.now()
                changed = SearchJob.objects.filter(
                    pk=job.pk, owner=request.user,
                    status__in=[SearchJob.Status.QUEUED, SearchJob.Status.RUNNING],
                ).update(
                    status=SearchJob.Status.CANCELLED,
                    completed_at=now,
                    error_summary="جست‌وجو به درخواست کاربر لغو شد؛ نتایج جمع‌آوری‌شده حفظ شده‌اند.",
                )
                if changed:
                    SourceExecution.objects.filter(
                        search_job_id=job.pk,
                        status__in=[SourceExecution.Status.QUEUED, SourceExecution.Status.RUNNING],
                    ).update(
                        status=SourceExecution.Status.CANCELLED,
                        completed_at=now,
                        error_details="جست‌وجو به درخواست کاربر لغو شد.",
                    )
                cancelled = bool(changed)
            break
        except OperationalError as exc:
            db = connections["default"]
            is_locked = "locked" in str(exc).lower() or "busy" in str(exc).lower()
            if db.vendor != "sqlite" or not is_locked:
                raise
            if attempt == 3:
                response = HttpResponse(
                    "پایگاه داده موقتاً مشغول است؛ چند ثانیه بعد دوباره لغو را بزنید.",
                    status=503,
                    content_type="text/plain; charset=utf-8",
                )
                response["Retry-After"] = "2"
                return response
            db.close()
            time.sleep(0.15 * (attempt + 1))
    if not cancelled:
        messages.info(request, "این جست‌وجو قبلاً پایان یافته است.")
        return redirect("job_detail", job_id=job.pk)
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


def _contact_payload(job):
    labels = {"neshan": "نشان", "balad": "بلد", "emalls": "ایمالز", "web": "وب"}
    results = []
    for contact in job.contacts.all():
        row = {
            "name": contact.business_name,
            "mobile": contact.normalized_number,
            "source": labels.get(contact.source_name, contact.source_name),
        }
        if contact.website:
            row["website"] = contact.website
        if contact.address:
            row["address"] = contact.address
        if contact.description:
            row["description"] = contact.description
        results.append(row)
    return results


@login_required
def export_json(request, job_id):
    job = owned_job(request.user, job_id)
    payload = {"requested_count": job.requested_phone_count, "found_count": job.contacts.count(), "results": _contact_payload(job)}
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="contacts-job-{job.pk}.json"'
    return response


def _excel_safe(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


@login_required
def export_excel(request, job_id):
    job = owned_job(request.user, job_id)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "شماره‌های تماس"
    sheet.append(["نام کسب‌وکار", "شماره موبایل", "منبع", "وب‌سایت", "نشانی", "توضیحات"])
    for contact, row in zip(job.contacts.all(), _contact_payload(job)):
        sheet.append([_excel_safe(row.get("name", "")), _excel_safe(row["mobile"]), _excel_safe(row["source"]), _excel_safe(row.get("website", "")), _excel_safe(row.get("address", "")), _excel_safe(row.get("description", ""))])
    for cell in sheet[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="153C35")
        cell.alignment = Alignment(horizontal="center")
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for column, width in {"A": 32, "B": 22, "C": 18, "D": 42, "E": 60, "F": 70}.items():
        sheet.column_dimensions[column].width = width
    output = BytesIO()
    workbook.save(output)
    response = HttpResponse(output.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="contacts-job-{job.pk}.xlsx"'
    return response


def health(request):
    return HttpResponse("ok", content_type="text/plain; charset=utf-8")
