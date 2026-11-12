from django.contrib import admin

from .models import BusinessLead, LeadEvidence, SearchJob, SourceExecution, SourceRateLimit, SourceToolCall


class SourceExecutionInline(admin.TabularInline):
    model = SourceExecution
    extra = 0
    readonly_fields = ("status", "started_at", "completed_at", "request_count", "result_count", "error_count")


@admin.register(SearchJob)
class SearchJobAdmin(admin.ModelAdmin):
    list_display = ("id", "trade_name", "geographic_scope_name", "status", "total_unique_businesses", "created_at")
    list_filter = ("status", "geographic_scope_type", "created_at")
    search_fields = ("trade_name", "geographic_scope_name", "owner__username")
    inlines = (SourceExecutionInline,)
    readonly_fields = ("started_at", "completed_at", "total_raw_results", "total_unique_businesses", "total_errors")


@admin.register(BusinessLead)
class BusinessLeadAdmin(admin.ModelAdmin):
    list_display = ("original_name", "city", "verification_status", "last_seen_at")
    list_filter = ("verification_status", "city")
    search_fields = ("original_name", "normalized_name", "address")


admin.site.register(LeadEvidence)
admin.site.register(SourceToolCall)


@admin.register(SourceRateLimit)
class SourceRateLimitAdmin(admin.ModelAdmin):
    list_display = ("source_name", "cooldown_until", "updated_at", "reason")
    readonly_fields = ("source_name", "cooldown_until", "updated_at", "reason")
