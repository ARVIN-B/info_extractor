import re

from django.db import migrations


ALLOWED_SOURCES = {"neshan", "balad", "emalls"}


def canonical_mobile(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    return digits if len(digits) == 11 and digits.startswith("09") else ""


def backfill_contacts(apps, schema_editor):
    BusinessPhone = apps.get_model("leads", "BusinessPhone")
    JobContact = apps.get_model("leads", "JobContact")
    alias = schema_editor.connection.alias
    batch = []

    rows = BusinessPhone.objects.using(alias).select_related("business_lead").prefetch_related("evidence").iterator(chunk_size=500)
    for phone in rows:
        lead = phone.business_lead
        evidence = next((item for item in phone.evidence.all() if item.source_name in ALLOWED_SOURCES), None)
        source = evidence.source_name if evidence else next((item for item in (lead.source_names or []) if item in ALLOWED_SOURCES), "")
        if not source:
            continue
        number = canonical_mobile(phone.normalized_number)
        if not number:
            continue
        batch.append(JobContact(
            search_job_id=lead.search_job_id,
            normalized_number=number,
            source_name=source,
            address=lead.address or "",
            evidence_url=(evidence.source_url if evidence else "") or "",
        ))
        if len(batch) >= 1000:
            JobContact.objects.using(alias).bulk_create(batch, ignore_conflicts=True, batch_size=1000)
            batch.clear()
    if batch:
        JobContact.objects.using(alias).bulk_create(batch, ignore_conflicts=True, batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [("leads", "0015_searchjob_requested_phone_count_jobcontact")]
    operations = [migrations.RunPython(backfill_contacts, migrations.RunPython.noop)]
