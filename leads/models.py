from django.conf import settings
from django.db import models
from django.utils import timezone


class SearchJob(models.Model):
    class ScopeType(models.TextChoices):
        CITY = "city", "شهر"
        PROVINCE = "province", "استان"
        IRAN = "iran", "سراسر ایران"

    class Status(models.TextChoices):
        QUEUED = "queued", "در صف"
        RUNNING = "running", "در حال اجرا"
        PARTIAL = "partial", "تکمیل با خطا"
        COMPLETED = "completed", "تکمیل‌شده"
        FAILED = "failed", "ناموفق"

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="search_jobs")
    trade_name = models.CharField("حوزهٔ کسب‌وکار", max_length=120)
    geographic_scope_type = models.CharField("نوع محدوده", max_length=12, choices=ScopeType.choices)
    geographic_scope_name = models.CharField("نام محدوده", max_length=120, blank=True)
    selected_sources = models.JSONField(default=list)
    max_results = models.PositiveSmallIntegerField(default=100)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    total_raw_results = models.PositiveIntegerField(default=0)
    total_unique_businesses = models.PositiveIntegerField(default=0)
    total_errors = models.PositiveIntegerField(default=0)
    error_summary = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.trade_name} / {self.get_geographic_scope_type_display()} / {self.pk}"


class SourceExecution(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "در صف"
        RUNNING = "running", "در حال اجرا"
        PARTIAL = "partial", "نیمه‌کامل"
        SKIPPED = "skipped", "موقتاً متوقف"
        COMPLETED = "completed", "تکمیل‌شده"
        FAILED = "failed", "ناموفق"

    search_job = models.ForeignKey(SearchJob, on_delete=models.CASCADE, related_name="source_executions")
    source_name = models.CharField(max_length=40)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.QUEUED)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveSmallIntegerField(default=0)
    result_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveSmallIntegerField(default=0)
    query_variants = models.JSONField(default=list, blank=True)
    areas_checked = models.JSONField(default=list, blank=True)
    truncated = models.BooleanField(default=False)
    error_details = models.TextField(blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["search_job", "source_name"], name="uniq_job_source")]
        ordering = ["source_name"]


class SourceToolCall(models.Model):
    source_execution = models.ForeignKey(SourceExecution, on_delete=models.CASCADE, related_name="tool_calls")
    tool_name = models.CharField(max_length=80)
    duration_ms = models.PositiveIntegerField(default=0)
    result_count = models.PositiveIntegerField(default=0)
    error_summary = models.CharField(max_length=500, blank=True)
    called_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["called_at", "id"]


class SourceRateLimit(models.Model):
    """Persistent per-source cooldown so later jobs respect upstream rate limits too."""

    source_name = models.CharField(max_length=40, unique=True)
    cooldown_until = models.DateTimeField(db_index=True)
    reason = models.CharField(max_length=160, blank=True)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["source_name"]


class SourcePlaceDetailCache(models.Model):
    """Short-lived, sanitized detail responses to avoid repeating provider calls."""

    source_name = models.CharField(max_length=40)
    source_record_id = models.CharField(max_length=255)
    detail_data = models.JSONField(default=dict)
    expires_at = models.DateTimeField(db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["source_name", "source_record_id"], name="uniq_source_place_detail_cache")]
        indexes = [models.Index(fields=["source_name", "expires_at"])]


class BusinessLead(models.Model):
    class Verification(models.TextChoices):
        DISCOVERED = "discovered", "کشف‌شده"
        SOURCE_CONFIRMED = "source_confirmed", "تأییدشده توسط منبع"
        CROSS_SOURCE = "cross_source_confirmed", "تأییدشده در چند منبع"
        INVALID = "invalid_format", "قالب شماره نامعتبر"
        CONFLICTING = "conflicting", "اطلاعات متعارض"
        UNVERIFIED = "unverified", "تأییدنشده"

    class PhoneStatus(models.TextChoices):
        FOUND_PUBLIC = "found_public", "تلفن عمومی پیدا شد؛ فعال بودن تأیید نشده"
        NOT_PROVIDED = "not_provided_by_source", "منبع تلفن ارائه نمی‌کند"
        NOT_FOUND = "not_found", "تلفن عمومی پیدا نشد"
        CONFLICTING = "conflicting", "تلفن‌ها متعارض‌اند"
        INVALID = "invalid", "قالب تلفن نامعتبر"
        NOT_CHECKED = "not_checked", "بررسی نشده"

    search_job = models.ForeignKey(SearchJob, on_delete=models.CASCADE, related_name="leads")
    normalized_name = models.CharField(max_length=255, db_index=True)
    original_name = models.CharField(max_length=255)
    phone_numbers = models.JSONField(default=list, blank=True)
    emails = models.JSONField(default=list, blank=True)
    social_urls = models.JSONField(default=list, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=120, blank=True, db_index=True)
    province = models.CharField(max_length=120, blank=True)
    website = models.URLField(max_length=500, blank=True)
    national_id = models.CharField(max_length=32, blank=True)
    business_type = models.CharField(max_length=40, blank=True)
    phone_status = models.CharField(max_length=32, choices=PhoneStatus.choices, default=PhoneStatus.NOT_CHECKED)
    confidence_score = models.FloatField(default=0.0)
    business_category = models.CharField(max_length=160, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    source_names = models.JSONField(default=list, blank=True)
    source_record_ids = models.JSONField(default=dict, blank=True)
    verification_status = models.CharField(max_length=32, choices=Verification.choices, default=Verification.DISCOVERED)
    first_seen_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["normalized_name", "city"]
        indexes = [models.Index(fields=["search_job", "city"]), models.Index(fields=["search_job", "verification_status"])]

    def __str__(self):
        return self.original_name


class LeadEvidence(models.Model):
    business_lead = models.ForeignKey(BusinessLead, on_delete=models.CASCADE, related_name="evidence")
    source_name = models.CharField(max_length=40)
    source_record_id = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    field_name = models.CharField(max_length=80)
    field_value = models.TextField(blank=True)
    normalized_value = models.TextField(blank=True)
    confidence_score = models.FloatField(default=0.0)
    validation_status = models.CharField(max_length=40, blank=True)
    data_type = models.CharField(max_length=40, default="public_business_data")
    extraction_method = models.CharField(max_length=40, default="mcp_tool_response")
    collected_at = models.DateTimeField(default=timezone.now)
    raw_response = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["collected_at", "field_name"]
        indexes = [models.Index(fields=["source_name", "source_record_id"])]

