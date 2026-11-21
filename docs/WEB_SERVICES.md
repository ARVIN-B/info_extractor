# سرویس‌های وب موردنیاز

اپلیکیشن دو endpoint داخلی را فراخوانی می‌کند: API جست‌وجوی SearXNG و API v2 مربوط به Firecrawl Self-hosted. نصب Python اضافی لازم نیست.

## SearXNG

یک SearXNG داخلی راه‌اندازی کنید و `json` را در `search.formats` فعال کنید. در غیر این صورت API ممکن است `403` برگرداند. نمونهٔ API که برنامه صدا می‌زند:

```text
GET /search?q=<query>&format=json&language=fa-IR&safesearch=1
```

آدرس نمونه در `.env`:

```dotenv
SEARXNG_BASE_URL=https://195.248.240.152:8888
SEARXNG_API_KEY=your-private-key
SEARXNG_TIMEOUT=30
SEARXNG_LANGUAGE=fa
SEARXNG_ENABLED=True
SEARXNG_MAX_PAGES=5
SEARXNG_MAX_QUERIES=3
SEARXNG_RETRIES=1
SEARXNG_VERIFY_TLS=True
SEARXNG_CA_BUNDLE=
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
WEB_CRAWL_MAX_PAGES_PER_DOMAIN=8
WEB_CRAWL_MAX_DEPTH=2
WEB_CRAWL_CONCURRENCY=1
WEB_CRAWL_TIMEOUT=60
```

سرویس Firecrawl برای شروع نباید از اینترنت عمومی قابل‌دسترسی باشد. دسترسی آن را به Django/Celery و شبکهٔ مدیریتی محدود کنید. Firecrawl برای crawl به صفحات هدف درخواست خروجی می‌فرستد؛ پس endpoint عمومی و دامنه‌های ورودی را در سطح شبکه کنترل کنید.

## بررسی اتصال

از همان محیط/شبکه‌ای که worker اجرا می‌شود بررسی کنید:

```powershell
Invoke-WebRequest 'https://195.248.240.152:8888/search?q=test&format=json&language=fa&pageno=1' -Headers @{ 'X-API-Key' = $env:SEARXNG_API_KEY }
Invoke-WebRequest -Method Post 'http://127.0.0.1:3002/v2/crawl' -ContentType 'application/json' -Body '{"url":"https://example.com","limit":1,"scrapeOptions":{"formats":["markdown"]}}'
```

```bash
curl 'https://195.248.240.152:8888/search?q=test&format=json&language=fa&pageno=1' -H "X-API-Key: $SEARXNG_API_KEY"
curl -X POST 'http://127.0.0.1:3002/v2/crawl' -H 'Content-Type: application/json' -d '{"url":"https://example.com","limit":1,"scrapeOptions":{"formats":["markdown"]}}'
```

برخی نصب‌های SearXNG فرمت JSON را غیرفعال می‌کنند. درخواست crawl نمونه یک crawl واقعی کوتاه شروع می‌کند؛ برای بررسی کامل، تست واقعی Crawl را با Job انجام دهید.

## مستندات upstream

- [SearXNG Search API](https://docs.searxng.org/dev/search_api.html)
- [Firecrawl self-hosting](https://docs.firecrawl.dev/contributing/self-host)
- [Firecrawl Crawl API](https://docs.firecrawl.dev/api-reference/endpoint/crawl)

## Production notes: TLS certificates and SQLite cancellation

If `SEARXNG_BASE_URL` uses an IP address such as `https://195.248.240.152:8888`, the certificate must include that IP in its Subject Alternative Name. A certificate issued only to a DNS hostname cannot validate for the IP. Prefer a DNS hostname with a valid certificate and configure that hostname as the base URL. For a private/self-signed CA, place its PEM file where both web and Celery worker can read it, set `SEARXNG_CA_BUNDLE=/app/certs/searxng-ca.pem`, then restart both services. Keep TLS verification enabled in production.

The currently observed certificate at `195.248.240.152:8888` is self-signed (`subject=issuer`) and its SAN contains the IP. That means the hostname matches, but the issuer is not in the worker's trust store. Obtain the PEM certificate/CA through an authenticated server administration channel, verify its SHA-256 fingerprint out of band, deploy the PEM to the app, and set the CA bundle path above. Alternatively, configure a publicly trusted certificate for a domain and switch the base URL to that domain.

SQLite is configured for WAL and a 60-second busy timeout, and job cancellation uses a short conditional update with bounded retries for transient `database is locked` errors. Keep `DATABASE_PATH` on persistent local disk, not a network filesystem. Restart web and workers after deploying. WAL does not remove contention from long or numerous concurrent writes; if lock errors continue, verify the database filesystem and worker logs, and consider PostgreSQL for higher concurrent write load.
# عیب‌یابی خطای اتصال وب

در خطای اتصال، صفحهٔ Job حالا نام سرویس، میزبان/درگاه تنظیم‌شده و نوع خطای شبکه یا کد HTTP را نشان می‌دهد؛ مسیر، query string و کلیدها در پیام خطا ثبت نمی‌شوند. اگر برنامه و worker داخل container هستند، `127.0.0.1` به همان container اشاره می‌کند؛ آدرس سرویس SearXNG و Firecrawl باید از شبکهٔ worker قابل دسترسی باشد. خطای `502` از SearXNG را در خود سرویس یا reverse proxy آن بررسی کنید و Firecrawl را از همان محیط worker با `GET /` یا endpoint health بررسی کنید.

`request_count` برای lane وب شامل یک درخواست جست‌وجوی SearXNG و هر درخواست شروع/poll Firecrawl است. یک crawl می‌تواند حداکثر ۸ صفحه را برگرداند؛ افزایش تعداد صفحه‌ها ممکن است به درخواست‌های poll بیشتر و اجرای طولانی‌تر منجر شود. مقدار هدف تماس، crawl دامنه‌های جدید را متوقف می‌کند.

## SearXNG: احراز هویت، TLS و جست‌وجوی کسب‌وکار

SearXNG فقط از HTTPS فراخوانی می‌شود و هر درخواست جست‌وجو header `X-API-Key` را از `SEARXNG_API_KEY` می‌گیرد. کلید در query، لاگ یا فایل خروجی قرار نمی‌گیرد. برای TLS، حالت پیش‌فرض اعتبارسنجی گواهی را فعال نگه می‌دارد. اگر گواهی خودامضا است، راه مطمئن این است که CA آن را در فایل قابل‌دسترسی worker قرار دهید و `SEARXNG_CA_BUNDLE` را به مسیر آن بدهید. فقط در صورت پذیرش آگاهانهٔ ریسک می‌توان اعتبارسنجی همان اتصال SearXNG را با `SEARXNG_VERIFY_TLS=False` غیرفعال کرد؛ این تنظیم SSL سایر سرویس‌ها را تغییر نمی‌دهد.

برنامه query صنف و شهر را با عبارت‌های فارسی و انگلیسی می‌سازد، از `pageno` برای خواندن تدریجی حداکثر `SEARXNG_MAX_PAGES` صفحه استفاده می‌کند و query تکراری را حذف می‌کند. هر صفحه یک درخواست شمرده می‌شود؛ یک retry محدود برای timeout/خطای شبکه و 5xx انجام می‌شود، اما 429 retry نمی‌شود و cooldown پایدار می‌گیرد. نتیجهٔ تکراری با URL نرمال‌شده ادغام می‌شود؛ مسیرهای متفاوت و زیردامنه‌ها حفظ می‌شوند. عنوان، snippet، engine، تاریخ انتشار و metadata در diagnostics منبع نگه‌داری می‌شوند. نتیجهٔ جست‌وجو سرنخ کشف است؛ تطبیق نام و محتوای سایت به‌تنهایی تأیید رسمی کسب‌وکار محسوب نمی‌شود.

تست زنده را از همان محیطی که Celery worker اجرا می‌شود اجرا کنید:

```bash
python manage.py check_searxng --query "فروشگاه الکترونیکی اصفهان شماره تماس" --page 1
```

فرمان فقط وضعیت اتصال و شمار نتایج/engineها را چاپ می‌کند و کلید را نمایش نمی‌دهد. خطای 401/403 را برای کلید یا فعال‌بودن JSON، خطای TLS را برای CA/SAN گواهی و timeout/اتصال را برای دسترسی worker و firewall بررسی کنید.
