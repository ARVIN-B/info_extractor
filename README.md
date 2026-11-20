# سامانهٔ استخراج شماره تماس کسب‌وکارها

این پروژه یک اپ Django برای یافتن شماره‌های موبایل عمومی کسب‌وکارهای ایران است. هر جست‌وجو چهار مسیر مستقل را هم‌زمان اجرا می‌کند: MCP نشان، MCP بلد، MCP ایمالز، و جست‌وجوی وب با SearXNG به‌علاوهٔ crawl سایت‌ها با Firecrawl Self-hosted.

## خروجی و شمارش

در شروع جست‌وجو، صنف، محدوده و تعداد شمارهٔ موردنیاز پرسیده می‌شود. هدف بر اساس **شمارهٔ موبایل یکتا در همان Job** است؛ منبعی که شماره را زودتر ثبت کند به‌عنوان منبع آن شماره نگه داشته می‌شود. خروجی هر ردیف فقط شامل شمارهٔ موبایل، نام منبع و در صورت موجود بودن نشانی است. شمارهٔ ثابت و ورودی نامعتبر رد می‌شوند. فرمت‌های `09…`، `+989…`، `00989…`، `9…` و `989…` پس از تبدیل ارقام فارسی/عربی به شکل `09XXXXXXXXX` ذخیره می‌شوند.

فیلتر «دارای تلفن» فقط وقتی به درخواست MCP اضافه می‌شود که schema همان ابزار فیلد Boolean سازگار را اعلام کند؛ در بقیهٔ موارد شماره‌ها پس از دریافت استخراج می‌شوند. خطا یا rate limit یک مسیر سه مسیر دیگر را متوقف نمی‌کند. سقف داخلی و نرخ upstream همچنان ممکن است باعث شود تعداد نهایی از هدف کمتر بماند.

## نیازمندی‌ها

- Python 3.11 یا جدیدتر
- Redis و Celery worker برای صف ناهمگام (یا broker فایل فقط برای توسعهٔ تک‌میزبان)
- یک نمونهٔ SearXNG با فرمت JSON فعال
- یک نمونهٔ Firecrawl Self-hosted سازگار با API نسخهٔ v2
- بسته‌های Python از `requirements.txt`

هیچ بسته‌ای را سراسری نصب نکنید. همهٔ فرمان‌های Python را با مفسر محیط پروژه اجرا کنید.

### Windows PowerShell

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (!(Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

در ترمینال جداگانه worker را اجرا کنید:

```powershell
.\.venv\Scripts\celery.exe -A config worker -l info --pool=solo
```

### Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py runserver 127.0.0.1:8000
```

در ترمینال جداگانه:

```bash
.venv/bin/celery -A config worker -l info
```

برای production از WSGI server و Redis استفاده کنید؛ `runserver` و broker فایل production نیستند. کارهای SQLite با چند writer به‌خاطر قفل فایل ممکن است کند شوند؛ برای workerهای هم‌زمان در production از PostgreSQL استفاده کنید.

## SearXNG و Firecrawl

راهنمای تنظیم SearXNG و Firecrawl Self-hosted در [docs/WEB_SERVICES.md](docs/WEB_SERVICES.md) است. آدرس سرویس‌ها باید از **محیط اجرای Django/Celery** قابل‌دسترسی باشد. اگر سرویس‌ها روی میزبان دیگری‌اند، URL همان میزبان را در `.env` بگذارید. SearXNG یک metasearch است و پوشش آن تابع موتورهای بالادست است.

## تنظیمات اصلی

در `.env` مقادیر زیر را تنظیم کنید:

- `SEARXNG_BASE_URL`: آدرس ریشهٔ SearXNG، مانند `http://127.0.0.1:8080`.
- `FIRECRAWL_BASE_URL`: آدرس ریشهٔ Firecrawl، مانند `http://127.0.0.1:3002`؛ کد مسیر `/v2` را اضافه می‌کند.
- `FIRECRAWL_API_KEY`: اختیاری؛ اگر نمونهٔ Firecrawl شما Bearer authentication را فعال کرده، کلید همان سرویس را در `.env` بگذارید.
- `WEB_SEARCH_ENABLED`: فعال/غیرفعال‌کردن lane وب.
- `WEB_SEARCH_MAX_RESULTS`, `WEB_SEARCH_MAX_DOMAINS`: سقف نتایج و دامنه‌ها.
- `WEB_CRAWL_MAX_PAGES_PER_DOMAIN`, `WEB_CRAWL_MAX_DEPTH`, `WEB_CRAWL_CONCURRENCY`, `WEB_CRAWL_TIMEOUT`, `WEB_SEARCH_TIMEOUT`: محدودیت منابع وب.
- `SEARCH_MAX_CONTACTS`: حداکثر هدف مجاز هر جست‌وجو.
- `ENABLED_MCP_SOURCES`: فقط `neshan,balad,emalls` پذیرفته می‌شود.
- `REDIS_URL` و `CELERY_BROKER_URL`: آدرس Redis و broker صف.
- `*_MCP_EXECUTABLE`: در صورت نیاز مسیر اجرایی هر MCP. مسیرهای پیش‌فرض از `.venv` پروژه انتخاب می‌شوند.

`FIRECRAWL_BASE_URL` و `SEARXNG_BASE_URL` را برای دسترسی از بیرون به شبکه عمومی منتشر نکنید؛ آن‌ها باید سرویس داخلی/خصوصی باشند. Crawl به همان دامنهٔ عمومی محدود، فقط HTTP(S)، با تعداد صفحه و عمق محدود انجام می‌شود.

## تست و عیب‌یابی

تست‌های پروژه آفلاین‌اند و برای اجرا به سرویس زندهٔ SearXNG، Firecrawl یا MCP نیاز ندارند:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test leads
```

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py test leads
```

اگر lane وب خطا دارد، در جزئیات Job خطای مستقل آن دیده می‌شود؛ نخست JSON بودن API در تنظیمات SearXNG و سپس دسترسی Django/Celery به endpointهای SearXNG و Firecrawl را بررسی کنید. Jobهای broker فایل به worker جداگانه نیاز دارند.
