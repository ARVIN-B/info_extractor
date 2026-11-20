# سرویس‌های وب موردنیاز

اپلیکیشن دو endpoint داخلی را فراخوانی می‌کند: API جست‌وجوی SearXNG و API v2 مربوط به Firecrawl Self-hosted. نصب Python اضافی لازم نیست.

## SearXNG

یک SearXNG داخلی راه‌اندازی کنید و `json` را در `search.formats` فعال کنید. در غیر این صورت API ممکن است `403` برگرداند. نمونهٔ API که برنامه صدا می‌زند:

```text
GET /search?q=<query>&format=json&language=fa-IR&safesearch=1
```

آدرس نمونه در `.env`:

```dotenv
SEARXNG_BASE_URL=http://127.0.0.1:8080
```

اگر Django داخل container است، `127.0.0.1` به همان container اشاره می‌کند؛ hostname سرویس را وارد کنید.

## Firecrawl Self-hosted

راهنمای فعلی upstream نسخهٔ Firecrawl `v2.11.162` را با Docker Compose اجرا می‌کند. در یک پوشهٔ جدا از پروژه:

```bash
git clone https://github.com/firecrawl/firecrawl.git
cd firecrawl
git checkout v2.11.162
```

در ریشهٔ همان checkout فایل `.env` سرویس Firecrawl را با مقادیر زیر بسازید؛ رمز PostgreSQL را با مقدار تصادفی قوی جایگزین کنید:

```dotenv
USE_DB_AUTHENTICATION=false
POSTGRES_USER=postgres
POSTGRES_PASSWORD=replace-with-a-long-random-secret
POSTGRES_DB=postgres
```

سپس `docker compose up --build -d` را اجرا کنید. این حالت احراز هویت API را خاموش می‌کند و فقط باید روی شبکهٔ مورداعتماد و محدود اجرا شود؛ آن را روی اینترنت منتشر نکنید. برای production تنظیمات امنیت، پایش، storage، پشتیبان‌گیری و recovery را طبق راهنمای رسمی کامل کنید.

endpointهای مورد انتظار برنامه `POST /v2/crawl` و `GET /v2/crawl/{id}` هستند. برنامه دامنهٔ شروع را از نتایج جست‌وجو می‌گیرد، عمق و تعداد صفحه را محدود می‌کند، مسیرهای اصلی/تماس/درباره/شعبه را بررسی می‌کند و لینک خارجی یا زیردامنه را دنبال نمی‌کند.

```dotenv
FIRECRAWL_BASE_URL=http://127.0.0.1:3002
WEB_CRAWL_MAX_PAGES_PER_DOMAIN=5
WEB_CRAWL_MAX_DEPTH=2
WEB_CRAWL_CONCURRENCY=3
WEB_CRAWL_TIMEOUT=60
```

سرویس Firecrawl برای شروع نباید از اینترنت عمومی قابل‌دسترسی باشد. دسترسی آن را به Django/Celery و شبکهٔ مدیریتی محدود کنید. Firecrawl برای crawl به صفحات هدف درخواست خروجی می‌فرستد؛ پس endpoint عمومی و دامنه‌های ورودی را در سطح شبکه کنترل کنید.

## بررسی اتصال

از همان محیط/شبکه‌ای که worker اجرا می‌شود بررسی کنید:

```powershell
Invoke-WebRequest 'http://127.0.0.1:8080/search?q=test&format=json'
Invoke-WebRequest -Method Post 'http://127.0.0.1:3002/v2/crawl' -ContentType 'application/json' -Body '{"url":"https://example.com","limit":1,"scrapeOptions":{"formats":["markdown"]}}'
```

```bash
curl 'http://127.0.0.1:8080/search?q=test&format=json'
curl -X POST 'http://127.0.0.1:3002/v2/crawl' -H 'Content-Type: application/json' -d '{"url":"https://example.com","limit":1,"scrapeOptions":{"formats":["markdown"]}}'
```

برخی نصب‌های SearXNG فرمت JSON را غیرفعال می‌کنند. درخواست crawl نمونه یک crawl واقعی کوتاه شروع می‌کند؛ برای بررسی کامل، تست واقعی Crawl را با Job انجام دهید.

## مستندات upstream

- [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)
- [Firecrawl self-hosting](https://docs.firecrawl.dev/contributing/self-host)
- [Firecrawl Crawl API](https://docs.firecrawl.dev/api-reference/endpoint/crawl)
