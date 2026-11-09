# سرنخ‌یاب | استخراج اطلاعات تماس کسب‌وکارها

اپ داخلی Django برای جست‌وجوی کسب‌وکارهای ایرانی از طریق MCPهای فقط‌خواندنی نشان و بلد. اطلاعات هر نتیجه همراه شناسه و شواهد منبع ذخیره می‌شود و خروجی Excel و JSON دارد. پردازش با Celery انجام می‌شود و SQLite دیتابیس پیش‌فرض است.

## وضعیت پیاده‌سازی

- رابط فارسی RTL برای ثبت جست‌وجو، مشاهدهٔ وضعیت، نتایج، فیلتر، صفحه‌بندی و شواهد.
- مدل job، اجرای مستقل هر منبع، کسب‌وکار، شواهد فیلدبه‌فیلد و گزارش زمان/تعداد/خطای هر فراخوانی MCP.
- کلاینت رسمی MCP Python SDK روی STDIO؛ ابزارها و schemaها از MCP واقعی خوانده و آرگومان‌ها پیش از فراخوانی بررسی می‌شوند.
- connectorهای انتخاب‌پذیر نشان و بلد. فقط جست‌وجوی مکان و دریافت جزئیات برای کسب‌وکارها استفاده می‌شود.
- نرمال‌سازی حروف و رقم فارسی، قالب تلفن و دامنه؛ ادغام محافظه‌کارانه بر اساس شناسهٔ مشترک یا تلفن/دامنه همراه با نام و نشانی یکسان.
- ورود Django و کنترل دسترسی بر اساس مالک job؛ خروجی‌ها نیازمند ورود هستند.
- تست‌های خودکار از دادهٔ mock استفاده می‌کنند و به وب‌سایت‌های زنده وصل نمی‌شوند.

این نسخه تماس با شماره‌ها نمی‌گیرد و فعال‌بودن یا تعلق شماره را تضمین نمی‌کند. منابع Classifieds و شماره‌های خصوصی در نسخهٔ نخست استفاده نمی‌شوند.

## منابع و ابزارهای متصل

| منبع | بستهٔ ثابت‌شده | ابزارها | وضعیت |
|---|---|---|---|
| نشان | `neshan-mcp==0.2.0` | `ns_search`, `ns_place` | جست‌وجو و جزئیات زنده بررسی شدند |
| بلد | `balad-mcp==0.2.0` | `bl_search`, `bl_place` | جست‌وجو و جزئیات زنده بررسی شدند |

Rasmio نیز بررسی شد اما در فهرست فعال منابع قرار نگرفت: ابزارهایش بر شرکت‌های ثبتی، مدیران و آگهی‌های رسمی تمرکز دارند، و README آن می‌گوید اطلاعات تماس اشخاص را برنمی‌گرداند و بازکردن پروندهٔ شرکت برای کاربر مهمان به حدود ۵ مورد در هر ۴ روز/IP محدود است. این محدودیت برای جست‌وجوی انبوه اطلاعات تماس مناسب نیست.

schemaهای ابزار از سرور در زمان اجرا فهرست می‌شوند. `ns_search` با پارامترهای مستندشدهٔ `query`, `near`, `limit` اجرا می‌شود و `ns_place` شناسه را در `place_id` می‌گیرد. `bl_search` از `query`, `lat`, `lng`, `limit` و `bl_place` از `id` استفاده می‌کند. ابزارهای جزئیات فقط وقتی شناسهٔ پایدار در نتایج باشد صدا زده می‌شوند.

نسخه‌ها بر اساس مخازن و README/کد سرورها بررسی شده‌اند: [مخزن اصلی iran-mcp](https://github.com/sepehr071/iran-mcp)، [کد Neshan](https://github.com/sepehr071/neshan-mcp)، [کد Balad](https://github.com/sepehr071/balad-mcp). این MCPها غیررسمی‌اند و رابط‌های عمومی وب را می‌خوانند؛ تغییر سایت یا محدودیت شبکه می‌تواند آن‌ها را از کار بیندازد. برای Neshan ممکن است دسترسی `ns_nearby` به اتصال داخل ایران نیاز داشته باشد؛ این MVP از آن ابزار استفاده نمی‌کند.

### پوشش جغرافیایی

- شهر: مراکز ۲۳ شهر موجود در کد Neshan مستقیماً پشتیبانی می‌شوند. برای شهر دیگر، برنامه ابتدا از ابزار نقشه مختصات می‌گیرد.
- استان: ابتدا مرکز استان با خود ابزار نقشه resolve می‌شود؛ جست‌وجو به اطراف همان نقطه محدود است.
- سراسر ایران: روی ۲۲ شهر شاخص، نمونه‌برداری محدود انجام می‌شود. هیچ‌کدام از این منابع تضمین نمی‌کنند که تمام کسب‌وکارهای کشور یا شهر پیدا شوند. صفحهٔ نتایج این محدودیت را باید در تفسیر خروجی لحاظ کند.
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
- `ENABLED_MCP_SOURCES`: فهرست منابع فعال با کاما؛ پیش‌فرض `neshan,balad`.
- `MCP_DISTRIBUTED_SOURCE_LIMITS`: در تولید فعال باشد؛ از Redis برای serialize کردن فراخوانی‌های هم‌زمان هر منبع استفاده می‌کند.
- `NESHAN_MCP_PROXY`, `BALAD_MCP_PROXY`: اختیاری؛ proxy منطبق با تنظیمات هر منبع.
- `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`: تنظیمات HTTPS. مقادیر نمونه برای استقرار HTTPS هستند.
- `SECURE_HSTS_PRELOAD`: به‌صورت پیش‌فرض خاموش است؛ فقط وقتی روشنش کن که همهٔ زیردامنه‌ها HTTPS دارند و قصد داری دامنه را برای فهرست preload مرورگرها ثبت کنی. در غیر این صورت هشدار `security.W021` در `check --deploy` آگاهانه باقی می‌ماند.

## اجرای محلی

ابتدا Redis باید در دسترس باشد. Redis خود برنامه در `.venv` نیست؛ فقط Python client آن در `.venv` نصب می‌شود. در تولید از Redis هم برای صف Celery و هم برای محدودکردن هم‌زمانی فراخوانی هر منبع استفاده می‌شود. اگر broker در دسترس نباشد، job با پیام مشخص خطا می‌گیرد و باید پس از راه‌اندازی Redis جست‌وجوی تازه‌ای ثبت شود. برای توسعهٔ محلی بدون Redis مقدار `MCP_DISTRIBUTED_SOURCE_LIMITS=False` بگذار؛ در آن حالت محدودیت هم‌زمانی بین‌پردازه‌ای فعال نیست.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
```

برای تولید کلید تصادفی از مفسر محلی پروژه استفاده کن:

```powershell
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(50))"
```

در دو پنجرهٔ PowerShell جدا:

```powershell
.\.venv\Scripts\celery.exe -A config worker --pool=solo -l info
```

```powershell
.\.venv\Scripts\python.exe manage.py runserver
```

بازکردن `http://127.0.0.1:8000/` کاربر را به ورود هدایت می‌کند. `createsuperuser` یک حساب کاربری کاری می‌سازد و همان کاربر به پنل مدیریت `/admin/` هم دسترسی دارد.

## Migration، بررسی و تست

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py test leads
```

## آزمون زندهٔ دستی MCP

این فرمان اختیاری به Neshan/Balad درخواست شبکه می‌فرستد. تست‌های عادی شبکهٔ زنده ندارند.

```powershell
.\.venv\Scripts\python.exe manage.py check_mcp --source all --query "طلافروشی" --city "تهران"
```

این فرمان یک جست‌وجوی کوچک زنده می‌فرستد و جزئیات یک نتیجه را هم می‌خواند؛ `results=0` ممکن است فقط به معنای نبود نتیجه برای همان عبارت/شهر باشد.

در بررسی زندهٔ انجام‌شده در این پروژه، جست‌وجو و خواندن جزئیات هر دو منبع موفق شد. آزمون ذخیره‌سازی زندهٔ نمونه نیز از هر منبع دو نتیجه گرفت و ۴ رکورد یکتا را با شواهد ثبت کرد؛ نتیجه‌ها موقتی بودند و پس از آزمون حذف شدند.

برای یک منبع:

```powershell
.\.venv\Scripts\python.exe manage.py check_mcp --source neshan --query "طلافروشی" --city "اصفهان"
.\.venv\Scripts\python.exe manage.py check_mcp --source balad --query "طلافروشی" --city "اصفهان"
```

## استقرار Linux / Windows

ابتدا Redis را به‌عنوان سرویسِ مدیریت‌شده یا نصب موجود آماده کن. برای استقرار سادهٔ single-host روی Linux:

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
- هیچ connector برای Divar/Sheypoor یا جمع‌آوری شمارهٔ شخصی آگهی‌ها فعال نیست.
