from urllib.parse import urlparse

from django.db import migrations


MAP_HOSTS = ("neshan.org", "balad.ir")


def _host(value):
    value = str(value or "").strip()
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower().removeprefix("www.")


def _normalize_website(value):
    value = str(value or "").strip()
    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if parsed.scheme not in {"http", "https"} or "." not in host:
        return ""
    clean = f"https://{host}"
    if parsed.path and parsed.path != "/":
        clean += parsed.path.rstrip("/")
    return clean


def correct_map_urls(apps, schema_editor):
    alias = schema_editor.connection.alias
    BusinessLead = apps.get_model("leads", "BusinessLead")
    LeadEvidence = apps.get_model("leads", "LeadEvidence")

    for lead in BusinessLead.objects.using(alias).exclude(website="").iterator():
        host = _host(lead.website)
        if not any(host == domain or host.endswith(f".{domain}") for domain in MAP_HOSTS):
            continue

        website_evidence = LeadEvidence.objects.using(alias).filter(
            business_lead_id=lead.pk, field_name="website"
        )
        alternatives = []
        for evidence in website_evidence:
            evidence_host = _host(evidence.field_value)
            if any(evidence_host == domain or evidence_host.endswith(f".{domain}") for domain in MAP_HOSTS):
                evidence.field_name = "provider_profile_url"
                evidence.data_type = "public_business_data"
                evidence.validation_status = "source_reported"
                evidence.save(update_fields=["field_name", "data_type", "validation_status"])
            else:
                normalized = _normalize_website(evidence.field_value)
                if normalized:
                    alternatives.append(normalized)

        # Preserve a separately evidenced business website if one was collected
        # from another source; otherwise clear the old map profile URL.
        website = alternatives[0] if alternatives else ""
        score = 0.35 + min(0.25, max(0, len(set(lead.source_names or [])) - 1) * 0.15)
        score += 0.15 if lead.phone_numbers else 0
        score += 0.10 if website else 0
        score += 0.05 if lead.emails else 0
        score += 0.10 if lead.national_id else 0
        if lead.verification_status == "conflicting":
            score -= 0.20
        score = round(max(0.0, min(1.0, score)), 2)
        BusinessLead.objects.using(alias).filter(pk=lead.pk).update(
            website=website, confidence_score=score
        )


class Migration(migrations.Migration):
    dependencies = [("leads", "0003_sourceexecution_areas_checked_and_more")]

    operations = [migrations.RunPython(correct_map_urls, migrations.RunPython.noop)]
