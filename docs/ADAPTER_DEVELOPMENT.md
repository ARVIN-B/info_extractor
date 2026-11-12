# افزودن MCP source

1. در [mcp_client.py](../leads/mcp_client.py) یک مدخل به `SOURCE_REGISTRY` اضافه کن: package pin‌شده، allowlist ابزارها، متغیر proxy اختیاری، نوع هدف، دسته‌های صنفی، فیلدهای واقعاً قابل دریافت، پوشش و محدودیت.
2. executable همان package را به `MCP_SERVER_PATHS` در `config/settings.py` اضافه کن و آن را در allowlist `ENABLED_MCP_SOURCES` بپذیر.
3. ابزار را از schema runtime در MCP بخوان. برای query و detail از نام فیلدهای live schema استفاده کن؛ هیچ پارامتری را حدس نزن. `MCPToolClient.call` schema را پیش از هر درخواست validate می‌کند.
4. برای workflow خاص، یک `SourceAdapter` در [adapters.py](../leads/adapters.py) پیاده کن. ابزارهای فقط‌خواندنی و لازم را صریحاً allowlist کن؛ پاسخ را به ردیف کسب‌وکار عمومی تبدیل کن، نه ردیف محصول/آگهی.
5. خروجی adapter را از `save_lead` عبور بده تا تماس، نوع کسب‌وکار و evidence مستقل ثبت شوند. فقط فیلدهای عمومی لازم در raw evidence ذخیره می‌شوند. فیلد خالی را با مقدار حدسی پر نکن.
6. `source_skip_reason` را برای applicability و مستندکردن دلیل skip به‌روزرسانی کن. در خطای منبع، نتایج منبع‌های دیگر و ردیف‌های قبلاً برگشته را حفظ کن.
7. برای 429 در fixture: `MCPSourceError` rate-limit را تشخیص می‌دهد، `SourceRateLimit` در SQLite cooldown را نگه می‌دارد، همان پاسخ جست‌وجو ذخیره می‌شود و call جدید در آن بازه skip می‌شود. هرگز برای دور زدن rate limit proxy را خودکار عوض نکن.
8. تست‌های offline موفق/ناقص/بدون تلفن/schema/timeout/429/dedup/export را بنویس. فقط تستی که با `LIVE_MCP_TESTS=1` یا فرمان `check_mcp` اجرا می‌شود مجاز است شبکهٔ بیرونی داشته باشد.
9. packageهای Python را فقط با `C:\Users\Arvin\Desktop\info_extractor\.venv\Scripts\python.exe -m pip install ...` نصب کن. نسخه را در `requirements.txt` پین کن. در deploy، بعد از install، `manage.py check_mcp --source <source>` و سپس migration/check/test را اجرا کن.

## جریان داده

`SearchJob` → `SourceExecution` → `SourceAdapter`/schema-checked MCP calls → normalize و conservative entity resolution → `BusinessLead` + `LeadEvidence` → owner-scoped UI/JSON/XLSX.

`BusinessLead.confidence_score` از قواعد deterministic و ثابت ساخته می‌شود: پایه 0.35؛ منبع مستقل دوم تا 0.25؛ تلفن عمومی 0.15؛ وب‌سایت 0.10؛ ایمیل 0.05؛ شناسهٔ ملی 0.10؛ تعارض 0.20 کسر. امتیاز، فعال بودن شماره یا پوشش کامل بازار را اثبات نمی‌کند. `LeadEvidence.validation_status` اعتبار فرمت را از تأیید مالکیت/فعال بودن جدا نگه می‌دارد.

## عملیات و محدودیت

- `SOURCE_TIMEOUT_SECONDS`, `SOURCE_MAX_CALLS_PER_JOB`, `MAX_MCP_CALLS_PER_JOB`, `SOURCE_RATE_LIMIT_COOLDOWN_SECONDS` بودجه و cooldown را کنترل می‌کنند. Queryها، مناطق بررسی‌شده و truncation هر source در `SourceExecution` ثبت می‌شوند.
- خطای HTTP/MCP مجاز است، اما درخواست‌های تکراری هنگام cooldown اجرا نمی‌شوند. source ممکن است در UI `partial`, `skipped` یا `failed` باشد.
- proxy اختیاری هر source از `.env` به همان MCP فرزند پاس داده می‌شود. این برنامه CAPTCHA، ورود، paywall یا محدودیت upstream را دور نمی‌زند.
- تغییر مدل نیازمند migration additive است. روی deploy، migration را جداگانه بازبینی و با دستور `manage.py migrate` در پنجرهٔ انتشار اعمال کن.
