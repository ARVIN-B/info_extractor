# ماتریس منابع جست‌وجو

این ماتریس وضعیت این checkout را از قابلیت‌های معرفی‌شده در catalog/repositoryهای MCP جدا می‌کند. هیچ source صرفاً به دلیل وجود در iran-mcp فعال نمی‌شود.

| منبع | ابزارهای بررسی‌شده/استفاده‌شده | فیلدهای واقع‌بینانه | پوشش و محدودیت | وضعیت این checkout |
|---|---|---|---|---|

| Neshan | `ns_search`, `ns_place` | نام، دسته، موقعیت، نشانی و تماس اگر خروجی عمومی بدهد؛ سایت فقط از فیلد صریح وب‌سایت | POI نقشه، سقف ابزار و محدودیت جغرافیایی؛ `ns_place` می‌تواند 429 بدهد | فعال؛ cooldown پایدار؛ live job در ۲۰۲۶-۱۱-۱۱ تعداد ۳۰ نتیجهٔ خام گرفت و سپس جزئیات با 429 محدود شد |
| Balad | `bl_nearby`, `bl_search`, `bl_place` | نام، دسته، نشانی، موقعیت و تماس اگر ارائه شود؛ سایت فقط از فیلد صریح وب‌سایت | POI نقشه؛ جست‌وجوی صنف با nearby؛ جغرافیا/تعداد نتیجه محدود | فعال؛ در live job نمونه ۲۰ نتیجهٔ خام برگشت |
| Emalls | `em_search` → `em_offers` → `em_shop`; `em_shops` برای resolve نام فروشگاه | نام فروشگاه، تلفن/نشانی/وب‌سایت فقط اگر پروفایل ارائه کند | فروشنده‌های حاضر در مقایسه‌گر قیمت؛ جست‌وجو از محصول به offer فروشگاه می‌رسد، بانک کامل اصناف نیست | فعال؛ package در `.venv` و schema زنده تأیید؛ smoke جست‌وجو موفق |
| Basalam | `bs_search` → `bs_vendor` | نام غرفه، شهر/فعالیت/روش ارسال و اطلاعات عمومی پروفایل؛ تلفن فقط اگر صریحاً برگردد | هر نتیجه از محصول به غرفه می‌رسد؛ غرفه معادل مغازهٔ فیزیکی نیست | فعال؛ package در `.venv` و schema زنده تأیید؛ smoke جست‌وجو موفق؛ شهر غرفه فیلتر می‌شود |
| Rasmio | `rs_search_companies`; `rs_company` عمداً فراخوانی خودکار نمی‌شود | شناسه ملی، نام، خلاصه فعالیت و هر فیلد عمومی موجود در نتایج جست‌وجو | فهرست ثبتی شرکت‌ها؛ پروندهٔ مهمان سهمیهٔ محدود دارد؛ تلفن اشخاص ارائه نمی‌شود | فعال فقط برای search؛ package و schema زنده تأیید؛ smoke موفق؛ برای تماس مستقیم منبع اصلی نیست |
| Torob | `tb_find_shops` | نام فروشگاه، شناسه و اطلاعات عمومی در صورت ارائه | جست‌وجوی مستقیم فروشگاه؛ تماس عمومی تضمین نمی‌شود؛ باید schema همان سرور بررسی شود | فعال؛ در نسخهٔ تولیدی `torob-mcp==0.2.2`، جست‌وجو از adapter واقعی استفاده می‌کند |
| Digikala | `dk_search` → `dk_product` | فروشنده/شناسهٔ فروشنده و اطلاعاتی که بازارگاه منتشر کند | فروشنده‌های محصولات جست‌وجوشده؛ وب‌سایت رسمی کسب‌وکار تضمین نمی‌شود | فعال؛ نسخهٔ تثبیت‌شده `digikala-mcp==0.6.2` |
| Iran Jobs | `job_companies` | نام شرکت و شواهد کارفرما/وب‌سایت در صورت ارائه | جست‌وجوی شرکت در IranTalent، Jobinja و Jobvision؛ تلفن عمومی تضمین نمی‌شود | فعال؛ نسخهٔ تولیدی `iran-jobs-mcp==0.2.1`؛ `name` از query داخلی بر اساس schema مپ می‌شود |
| SnappShop | `ss_search` → `ss_product` | فروشنده/شناسهٔ فروشنده و اطلاعاتی که بازارگاه منتشر کند | فروشنده‌های محصولات جست‌وجوشده؛ ممکن است به خروجی شبکهٔ ایران نیاز داشته باشد | فعال؛ نسخهٔ تثبیت‌شده `snappshop-mcp==0.2.1` |
| Divar و Sheypoor | ابزارهای آگهی و جست‌وجوی آگهی | عنوان/دسته/شهر به‌عنوان lead، فقط اگر دادهٔ عمومی و مجاز باشد | شمارهٔ شخصی فروشنده/آگهی‌دهنده خارج از محدوده است؛ آگهی اثبات کسب‌وکار مستقل نیست | غیرفعال؛ هیچ تماس شخصی استخراج نمی‌شود |
| Snappfood، TapsiFood، Okala | ابزارهای فروشگاه/رستوران و محدودهٔ تحویل | نام فروشنده و دادهٔ سرویس/نشانی در صورت ارائه | محدودهٔ تحویل پلتفرم است، نه فهرست همهٔ رستوران‌ها/فروشگاه‌ها؛ تلفن عمومی تضمین نمی‌شود | غیرفعال؛ adapter صنفی فقط پس از بررسی schema و coverage |
| Paziresh24، Doctoreto، ExirYab | جست‌وجوی پزشک/مرکز درمانی | پروفایل حرفه‌ای و اطلاعات تماس عمومی در صورت ارائه | فقط حوزه سلامت؛ نتیجهٔ پزشک با کسب‌وکار عمومی یکی نیست | غیرفعال؛ نیازمند adapter/تست مستقل حوزه سلامت |
| OpenStreetMap/Overpass | API عمومی OSM | تگ‌های POI، نام، نشانی و contact tags در صورت ثبت | کیفیت/تازگی داده ناهمگون؛ attribution و rate limit الزامی؛ query باید کنترل‌شده باشد | در این نسخه پیاده‌سازی نشده؛ پیش از فعال‌سازی policy و attribution جداگانه بررسی شود |

## سیاست اجرا

- فهرست `ENABLED_MCP_SOURCES` در `.env` تعیین می‌کند کدام منابع فعال‌اند؛ تنظیم `.env` کاربر دست نخورده می‌ماند. جست‌وجوی `check_mcp --schema-only` فقط اتصال و قرارداد ابزار را می‌سنجد و فراخوانی وب‌سایت انجام نمی‌دهد.
- جست‌وجوی Emalls و Basalam از محصول به فروشنده می‌رسد؛ خروجی محصول به‌تنهایی به‌عنوان شرکت/مغازه ثبت نمی‌شود.
- رسمیو فقط جست‌وجوی کم‌هزینهٔ شرکت را انجام می‌دهد؛ عمداً `rs_company` را خودکار صدا نمی‌زند تا سهمیهٔ محدود کاربر مهمان مصرف نشود.
- خطای 429 در SQLite تا زمان cooldown می‌ماند. منبع در آن بازه `skipped` است؛ خطای source جزئی `partial` است و نتایج جست‌وجوی همان پاسخ حفظ می‌شوند.
- درخواست‌های `ns_place` حداقل با فاصلهٔ ۶ ثانیه می‌روند و detailهای پاک‌سازی‌شده تا یک روز cache می‌شوند؛ داده‌های cacheشدهٔ قبلی از evidence موجود seed می‌شوند. این کار تماس تکراری و burst را کم می‌کند، اما quota بیرونی را حذف نمی‌کند.
- queryهای کشور budget دارند؛ جست‌وجوی ۲۳ شهر فعلی نمونه‌برداری است، نه پوشش کامل ایران. سقف call هر source و کل job در `SOURCE_MAX_CALLS_PER_JOB` و `MAX_MCP_CALLS_PER_JOB` کنترل می‌شود؛ query و منطقهٔ بررسی‌شده و truncation در اجرای منبع ثبت می‌شوند.
- فیلد عمومی `url` در پاسخ نقشه، صفحهٔ خود Neshan/Balad است و وب‌سایت محسوب نمی‌شود؛ برای `BusinessLead.website` فقط کلیدهای صریح `website`/`web`/پیوند سایت کسب‌وکار پذیرفته می‌شوند. شواهد لینک صفحهٔ نقشه را جدا نگه می‌دارند.
- Jobهای پس‌زمینه به Celery worker نیاز دارند؛ اجرای `runserver` به‌تنهایی jobها را پردازش نمی‌کند. صفحهٔ job پس از یک دقیقه ماندن در صف راه‌اندازی worker را یادآوری می‌کند.
- برای بازبینی schema بدون فراخوانی وب از `check_mcp --schema-only` استفاده کن؛ smoke قبلی هر منبع محدود بوده و دسترسی/محدودیت سرویس بیرونی ممکن است تغییر کند.

## مراجع اصلی

- [iran-mcp catalog](https://github.com/sepehr071/iran-mcp) و فایل‌های `servers.json`, `TOOLS.md`, `AGENTS.md`
- [Emalls MCP](https://github.com/sepehr071/emalls-ir-mcp)
- [Basalam MCP](https://github.com/sepehr071/basalam-mcp)
- [Rasmio MCP](https://github.com/sepehr071/rasmio-mcp)
- [Torob MCP](https://github.com/sepehr071/torob-mcp)
- [Neshan MCP](https://github.com/sepehr071/neshan-mcp)

For Emalls, Basalam, and Rasmio, the planner now tries source-specific nearby query variants instead of marking the source irrelevant and skipping it. The exact attempted phrases are recorded on the source card. Marketplace and registry matches can be related alternatives rather than the same type of storefront; interpret each result using its source and business category.
