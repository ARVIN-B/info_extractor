from django import forms
from django.conf import settings

from .models import SearchJob
from .normalization import normalize_text
from .mcp_client import SOURCE_REGISTRY


class SearchJobForm(forms.Form):
    trade_name = forms.CharField(label="صنف یا حوزهٔ کسب‌وکار", max_length=120, min_length=2)
    geographic_scope_type = forms.ChoiceField(label="محدوده", choices=SearchJob.ScopeType.choices)
    geographic_scope_name = forms.CharField(label="شهر یا استان", max_length=120, required=False)
    sources = forms.MultipleChoiceField(label="منابع", choices=[(key, key.title()) for key in SOURCE_REGISTRY if key in settings.ENABLED_MCP_SOURCES], widget=forms.CheckboxSelectMultiple)
    max_results = forms.IntegerField(label="حداکثر نتیجه", min_value=1, max_value=500, initial=100)

    def clean_trade_name(self):
        value = " ".join(self.cleaned_data["trade_name"].split())
        if not normalize_text(value):
            raise forms.ValidationError("نام صنف معتبر نیست.")
        return value

    def clean(self):
        cleaned = super().clean()
        scope_type = cleaned.get("geographic_scope_type")
        scope_name = " ".join((cleaned.get("geographic_scope_name") or "").split())
        if scope_type in {SearchJob.ScopeType.CITY, SearchJob.ScopeType.PROVINCE} and not scope_name:
            self.add_error("geographic_scope_name", "برای جست‌وجوی شهر یا استان نام محدوده را وارد کنید.")
        if scope_type == SearchJob.ScopeType.IRAN:
            cleaned["geographic_scope_name"] = "ایران"
        return cleaned
