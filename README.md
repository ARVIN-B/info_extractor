# سرنخ‌یاب | استخراج اطلاعات تماس کسب‌وکارها

اپ داخلی Django برای کشف کسب‌وکارهای ایران از راه چند منبع MCP فقط‌خواندنی. نتایج با شواهد فیلدبه‌فیلد ذخیره و به JSON و Excel صادر می‌شوند. پردازش با Celery انجام می‌شود و SQLite دیتابیس پیش‌فرض است.

## وضعیت پیاده‌سازی

- رابط فارسی RTL برای ثبت جست‌وجو، گزارش source-level، نتایج، فیلتر، صفحه‌بندی و شواهد.
- مدل job، اجرای مستقل هر منبع، تماس عمومی، ایمیل، شبکهٔ اجتماعی، شناسهٔ ثبتی، evidence هر فیلد و گزارش زمان/تعداد/خطای هر فراخوانی MCP.
- کلاینت رسمی MCP Python SDK روی STDIO؛ ابزارها و schemaها از MCP واقعی خوانده و آرگومان‌ها پیش از فراخوانی بررسی می‌شوند.
- connector فعال فعلی نشان و بلد؛ adapterهای ایمالز، باسلام و رسمیو در registry جداگانه آماده‌اند و تا نصب/تأیید schema در `.venv` فعال نمی‌شوند.
- نرمال‌سازی حروف و رقم فارسی، قالب تلفن و دامنه؛ ادغام محافظه‌کارانه بر اساس شناسهٔ مشترک یا تلفن/دامنه همراه با نام و نشانی یکسان.
- ورود Django و کنترل دسترسی بر اساس مالک job؛ خروجی‌ها نیازمند ورود هستند.
- تست‌های خودکار از دادهٔ mock استفاده می‌کنند و به وب‌سایت‌های زنده وصل نمی‌شوند.

این نسخه تماس با شماره‌ها نمی‌گیرد و فعال‌بودن یا تعلق شماره را تضمین نمی‌کند. ۴۲۹ منبع باعث توقف callهای بعدی، ثبت cooldown در SQLite و وضعیت partial/skipped می‌شود؛ نتیجه‌های همان پاسخ جست‌وجو نگه داشته می‌شوند. محدودیت منبع به معنی صفر نتیجه نیست. منابع Classifieds و شماره‌های خصوصی استفاده نمی‌شوند.

## منابع و ابزارهای متصل

| منبع | بستهٔ ثابت‌شده | ابزارها | وضعیت |
|---|---|---|---|
| نشان | `neshan-mcp==0.2.0` | `ns_search`, `ns_place` | جست‌وجو و جزئیات زنده بررسی شدند |
| بلد | `balad-mcp==0.2.0` | `bl_nearby`, `bl_search` (رفع ابهام شهر), `bl_place` | جست‌وجوی صنف با `bl_nearby` و جزئیات زنده بررسی شدند |
| ایمالز | `emalls-ir-mcp==0.2.0` | `em_search`, `em_offers`, `em_shop` | فعال؛ adapter محصول→offer→پروفایل فروشگاه؛ schema و smoke جست‌وجو بررسی شدند |
| باسلام | `basalam-mcp==0.2.0` | `bs_search`, `bs_vendor` | فعال؛ adapter محصول→پروفایل غرفه؛ تلفن عمومی تضمین نمی‌شود؛ schema و smoke جست‌وجو بررسی شدند |
| رسمیو | `rasmio-mcp==0.2.0` | `rs_search_companies` | فعال برای جست‌وجوی شرکت/شناسه ملی؛ schema و smoke بررسی شدند؛ پروفایل خودکار باز نمی‌شود تا سهمیهٔ مهمان حفظ شود |

سه connector منتخب داخل `.venv` نصب و schema زندهٔ ابزارهای لازم تأیید شد. نصب سراسری انجام نشده است. تنظیم این checkout منابع Neshan، Balad، Emalls، Basalam و Rasmio را فعال می‌کند؛ مقدار واقعی `.env` محرمانه و خارج از مستندات است.

Rasmio نیز بررسی شد اما در فهرست فعال منابع قرار نگرفت: ابزارهایش بر شرکت‌های ثبتی، مدیران و آگهی‌های رسمی تمرکز دارند، و README آن می‌گوید اطلاعات تماس اشخاص را برنمی‌گرداند و بازکردن پروندهٔ شرکت برای کاربر مهمان به حدود ۵ مورد در هر ۴ روز/IP محدود است. این محدودیت برای جست‌وجوی انبوه اطلاعات تماس مناسب نیست.

schemaهای ابزار از سرور در زمان اجرا فهرست می‌شوند. `ns_search` با `query`, `near`, `limit` اجرا می‌شود و `ns_place` شناسه را در `place_id` می‌گیرد. برای جست‌وجوی صنف در بلد، `bl_nearby` با عبارت آزاد صنف، مختصات، شعاع و سقف نتیجه استفاده می‌شود؛ `bl_search` فقط برای resolve کردن شهرهای ناشناخته است. `bl_place` شناسه را در `id` می‌گیرد. ابزارهای جزئیات فقط وقتی شناسهٔ پایدار در نتایج باشد صدا زده می‌شوند.

نسخه‌ها بر اساس مخازن و README/کد سرورها بررسی شده‌اند: [مخزن اصلی iran-mcp](https://github.com/sepehr071/iran-mcp)، [کد Neshan](https://github.com/sepehr071/neshan-mcp)، [کد Balad](https://github.com/sepehr071/balad-mcp). این MCPها غیررسمی‌اند و رابط‌های عمومی وب را می‌خوانند؛ تغییر سایت یا محدودیت شبکه می‌تواند آن‌ها را از کار بیندازد. برای Neshan ممکن است دسترسی `ns_nearby` به اتصال داخل ایران نیاز داشته باشد؛ این MVP از آن ابزار استفاده نمی‌کند.

### پوشش جغرافیایی

- شهر: مراکز ۲۳ شهر موجود در کد Neshan مستقیماً پشتیبانی می‌شوند. برای شهر دیگر، برنامه ابتدا از ابزار نقشه مختصات می‌گیرد.
- استان: ابتدا مرکز استان با خود ابزار نقشه resolve می‌شود؛ جست‌وجو به اطراف همان نقطه محدود است.
- سراسر ایران: روی ۲۳ شهر شاخص، نمونه‌برداری محدود انجام می‌شود. هیچ‌کدام از این منابع تضمین نمی‌کنند که تمام کسب‌وکارهای کشور یا شهر پیدا شوند. صفحهٔ نتایج این محدودیت را باید در تفسیر خروجی لحاظ کند.
- حداکثر نتیجه ۵۰۰ است و بودجهٔ بین منابع تقسیم می‌شود. هر منبع و هر فراخوانی timeout دارد؛ خطای یک منبع باید در صفحهٔ job جدا ثبت شود.

## نصب فقط داخل `.venv`

در PowerShell، از ریشهٔ پروژه:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

تمام وابستگی‌های Python به‌وسیلهٔ مفسر همین `.venv` نصب می‌شوند. برای اتصال MCP به‌جای `uvx` از executableهای نصب‌شده در `.venv\Scripts` استفاده می‌شود؛ `uvx` بسته‌ها را در cache جدا نصب می‌کند و برای این پروژه مناسب نیست. فایل `requirements-production.txt` فقط روی میزبان Linux لازم است و Gunicorn را به همین محیط مجازی میزبان اضافه می‌کند.

در `.env` مقدار `DJANGO_SECRET_KEY` را به کلید تصادفی بلند تغییر بده. متغیرهای لازم:

برای اجرای محلی بدون HTTPS، در `.env` این مقادیر را قرار بده: `DJANGO_DEBUG=True`, `SECURE_SSL_REDIRECT=False`, `SESSION_COOKIE_SECURE=False`, `CSRF_COOKIE_SECURE=False`. فایل نمونه مقادیر مناسب HTTPS در سرور را نشان می‌دهد و به‌تنهایی تنظیم آمادهٔ `runserver` نیست.

- `DJANGO_SECRET_KEY`: کلید Django تصادفی و محرمانه.
- `DJANGO_DEBUG`: در سرور `False`.
- `DJANGO_ALLOWED_HOSTS`: فهرست میزبان‌ها با کاما.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: origin کامل، مثل `https://example.com`.
- `REDIS_URL`: آدرس broker Celery.
- `DATABASE_PATH`: مسیر فایل SQLite؛ پیش‌فرض `db.sqlite3` کنار `manage.py`.
- `SOURCE_TIMEOUT_SECONDS`: timeout هر شروع/فراخوانی MCP، پیش‌فرض ۴۵ ثانیه.
- `SOURCE_LOCK_WAIT_SECONDS`: حداکثر انتظار برای نوبت فراخوانی منبع، پیش‌فرض ۶۰ ثانیه.
- `SOURCE_MAX_CALLS_PER_JOB`: سقف callهای MCP برای هر source در یک job، پیش‌فرض ۴۰.
- `MAX_MCP_CALLS_PER_JOB`: سقف مجموع callهای MCP بین همهٔ منابع یک job، پیش‌فرض ۱۰۰.
- `SOURCE_RATE_LIMIT_COOLDOWN_SECONDS`: cooldown پیش‌فرض پس از 429 وقتی منبع زمان انتظار دقیق نداده، پیش‌فرض ۶۰ ثانیه.
- `SOURCE_DETAIL_CACHE_TTL_SECONDS`: مدت نگهداری پاسخ جزئیات عمومی مکان برای جلوگیری از درخواست تکراری؛ پیش‌فرض ۸۶۴۰۰ ثانیه (یک روز).
- `ENABLED_MCP_SOURCES`: فهرست منابع فعال با کاما؛ پیش‌فرض `neshan,balad`؛ در `.env` این checkout پنج منبع Neshan، Balad، Emalls، Basalam و Rasmio فعال‌اند.
- `MCP_DISTRIBUTED_SOURCE_LIMITS`: در تولید فعال باشد؛ از Redis برای serialize کردن فراخوانی‌های هم‌زمان هر منبع استفاده می‌کند.
- `NESHAN_MCP_PROXY`, `BALAD_MCP_PROXY`, `EMALLS_MCP_PROXY`, `BASALAM_MCP_PROXY`, `RASMIO_MCP_PROXY`: اختیاری؛ فقط در صورت نیاز و بر اساس تنظیمات همان منبع.
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`: تنظیمات HTTPS. مقادیر نمونه برای استقرار HTTPS هستند.
- `SECURE_HSTS_PRELOAD`: به‌صورت پیش‌فرض خاموش است؛ فقط وقتی روشنش کن که همهٔ زیردامنه‌ها HTTPS دارند و قصد داری دامنه را برای فهرست preload مرورگرها ثبت کنی. در غیر این صورت هشدار `security.W021` در `check --deploy` آگاهانه باقی می‌ماند.

## اجرای محلی

در تولید Redis سرویس broker صف Celery و محدودکنندهٔ هم‌زمانی منابع است. برای توسعهٔ تک‌میزبان بدون Redis، `CELERY_BROKER_URL=filesystem://` و `MCP_DISTRIBUTED_SOURCE_LIMITS=False` بگذار؛ صف فایل فقط برای توسعه است و باید worker جداگانه اجرا شود. فایل‌های صف در `var/celery-broker/` نگه‌داری می‌شوند.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

برای تولید کلید تصادفی از مفسر محلی پروژه استفاده کن:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

### ویندوز (دو پنجرهٔ PowerShell جدا)

```powershell
.\.venv\Scripts\python.exe -m celery -A config worker --pool=solo -l info
```

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

### لینوکس (دو ترمینال جدا)

```bash
.venv/bin/python -m celery -A config worker -l info
```

```bash
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

جست‌وجو بدون Celery worker در صف باقی می‌ماند. اگر job بیش از یک دقیقه در صف بماند، صفحهٔ job راه‌اندازی worker را یادآوری می‌کند.

بازکردن `http://127.0.0.1:8000/` کاربر را به ورود هدایت می‌کند. `createsuperuser` یک حساب کاربری کاری می‌سازد و همان کاربر به پنل مدیریت `/admin/` هم دسترسی دارد.

## Migration، بررسی و تست

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test leads
```

## آزمون زندهٔ دستی MCP

تست‌های خودکار شبکهٔ بیرونی ندارند. برای smoke test زنده، هر منبع را جداگانه اجرا کن تا خروجی و rate limit یک سرویس روی سرویس دیگر اثر نگذارد:

```powershell
.\.venv\Scripts\python.exe manage.py check_mcp --source balad --query "آزمایشگاه" --city "تهران"
.\.venv\Scripts\python.exe manage.py check_mcp --source emalls --query "عسل طبیعی" --city "تهران"
.\.venv\Scripts\python.exe manage.py check_mcp --source basalam --query "عسل طبیعی" --city "تهران"
.\.venv\Scripts\python.exe manage.py check_mcp --source rasmio --query "شرکت مواد غذایی" --city "تهران"
```

برای نشان، فقط وقتی cooldown/rate limit فعال نیست smoke test بگیر؛ این فرمان search و جزئیات یک نتیجه را صدا می‌زند و ممکن است محدودیت `ns_place` را فعال کند:

```powershell
.\.venv\Scripts\python.exe manage.py check_mcp --source neshan --query "آزمایشگاه" --city "تهران"
```

در آزمون زندهٔ ۲۰۲۶-۱۱-۱۱، بلد در جست‌وجوی job نمونه ۲۰ نتیجهٔ خام داد؛ نشان ۳۰ نتیجه داد اما جزئیات یک مکان با HTTP 429 محدود شد و job به‌صورت partial باقی ماند. smokeهای جداگانهٔ ایمالز/باسلام/رسمیو به‌ترتیب ۱ محصول با پروفایل، ۳ نتیجه با پروفایل غرفه و ۳ شرکت در جست‌وجو برگرداندند. پاسخ صفر برای یک عبارت به‌تنهایی سلامت یا پوشش کامل منبع را ثابت نمی‌کند.

برای کاهش 429 نشان، `ns_place`ها با فاصلهٔ ۶ ثانیه فراخوانی می‌شوند و جزئیات امن تا یک روز در SQLite cache می‌شوند. پس از 429 درخواست‌های بعدی متوقف می‌شوند و نتایج جست‌وجوی جاری حفظ می‌شوند. این کار فشار تکراری را کم می‌کند اما سهمیه یا دسترس‌پذیری Neshan را تضمین نمی‌کند.

URL عمومی `url` در نتایج نقشه فقط به‌عنوان صفحهٔ منبع نگهداری می‌شود. فیلد وب‌سایت کسب‌وکار فقط از فیلد صریح `website`/`web`/لینک وب فروشگاه پر می‌شود؛ migration نسخهٔ `0004` آدرس‌های map provider ذخیره‌شدهٔ قدیمی را نیز از وب‌سایت کسب‌وکار جدا می‌کند.

برای یک منبع:

```powershell
.\.venv\Scripts\python.exe manage.py check_mcp --source neshan --query "طلافروشی" --city "اصفهان"
.\.venv\Scripts\python.exe manage.py check_mcp --source balad --query "طلافروشی" --city "اصفهان"
```

## استقرار Linux / Windows

Redis را به‌عنوان سرویسِ مدیریت‌شده یا نصب موجود آماده کن. برای استقرار سادهٔ single-host روی Linux:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-production.txt
cp .env.example .env
# مقادیر .env را با SECRET_KEY، دامنه، Redis و HTTPS تکمیل کن.
./.venv/bin/python manage.py migrate
./.venv/bin/python manage.py collectstatic --noinput
./.venv/bin/python manage.py createsuperuser
./.venv/bin/gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 2 --timeout 60
./.venv/bin/celery -A config worker --loglevel=INFO --concurrency=1
./.venv/bin/celery -A config beat --loglevel=INFO
```

Gunicorn، Celery worker و Celery beat را به‌صورت سرویس‌های مستقل زیر process supervisor میزبان اجرا کن و HTTPS را در reverse proxy خاتمه بده. Beat jobهایی را که worker بیش از ۲۰ دقیقه رها کرده دوباره در صف می‌گذارد؛ برای راه‌اندازی بازیابی خودکار هر سه process لازم‌اند. چون این checkout تنظیمات میزبان تولیدی یا systemd موجودی نداشت، فایل service یا Nginx مختص سروری نامعلوم ساخته نشده است. روی Windows سرور می‌توان WSGI را با `waitress-serve --listen=127.0.0.1:8000 config.wsgi:application` در `.venv` اجرا کرد؛ Redis و worker Celery باید همچنان سرویس‌های جداگانه باشند. از SQLite روی یک میزبان و یک worker محدود استفاده کن و فایل DB را روی فایل‌سیستم پایدار نگه دار.

Health check عمومی `GET /health/` متن `ok` می‌دهد و شامل اطلاعاتی از سیستم نیست. خطاهای فنی در log سرور نگه‌داری می‌شوند؛ متن exception نامنتظره به کاربر نمایش داده نمی‌شود.

## آزمون جست‌وجوی نمونه

از فرم، صنف «طلافروشی»، محدودهٔ شهر «اصفهان»، هر دو منبع و مثلاً ۵۰ نتیجه را انتخاب کن. برای کارکرد زنده Redis و Celery و دسترسی شبکه به سرورها لازم است. خروجی‌ها از رکوردهای دیتابیس ساخته می‌شوند. جزئیات هر کسب‌وکار پیوند منبع و شواهد فیلدها را نشان می‌دهد.

## نگه‌داری

- پیش از به‌روزرسانی، نسخه‌های بسته‌های MCP و schema واقعی ابزارها را دوباره بررسی کن؛ تغییر خروجی منبع نیازمند تغییر adapter و تست mock است.
- بکاپ منظم `DATABASE_PATH` بگیر. نتیجه‌ها و پاسخ‌های خام می‌توانند حاوی اطلاعات تماس عمومی باشند.
- برای خطاها صفحهٔ job، `SourceExecution`, `SourceToolCall` و log worker را بررسی کن.
- cooldown rate limit در جدول `SourceRateLimit` نگه داشته می‌شود؛ اگر منبع skip شد، زمان پایان cooldown و علت در گزارش source می‌آید. نتیجهٔ خالی برای منبع skipشده یا partial معادل «هیچ کسب‌وکاری وجود ندارد» نیست.
- هیچ connector برای Divar/Sheypoor یا جمع‌آوری شمارهٔ شخصی آگهی‌ها فعال نیست.
