# Raw MCP search responses for the exact query `الکترونیکی`

Captured: 2026-11-20 (Asia/Tehran). This file contains one search-tool call per configured source, using each live MCP schema and the project's search-argument mapping. No product/vendor/place detail calls, pagination, query expansion, or automatic retries were made.

Public business contact fields are retained as returned, including public phone values. Values nested in account/personal-profile fields and secret-bearing fields are redacted. This is necessary because some MCP results may include non-public account data; no private account data was requested or used.

## Search-sample findings

One first-page search response was captured from each source. No detail/profile endpoint, next page, or query variant was called. Search defaults are in effect where the request omits location or optional filters; Neshan and Balad used their Tehran defaults.

| Source | Search records in returned data | Phone fields in this search response | Valid mobile candidates |
|---|---:|---|---:|
| Neshan | 10 places | 9 `results[].phone` values: 6 landlines and 3 mobiles | 3 |
| Balad | 10 places | 7 `results[].phone` values; all are landlines | 0 |
| Emalls | 10 products | No phone field | 0 |
| Basalam | 10 products | No phone field | 0 |
| Rasmio | 10 companies | No phone field | 0 |
| Torob | 10 shops | No phone field | 0 |
| Iran Jobs | 29 companies (11 IranTalent, 8 Jobinja, 10 Jobvision) | No phone field | 0 |
| Quera | 3 companies | No phone field | 0 |
| Digikala | 22 products | No phone field | 0 |
| SnappShop | 12 products | No phone field | 0 |

This supports a likely reason for the low success count: the mobile-only rule excludes map results that publish landlines, and most non-map search endpoints returned products/companies without contact numbers in this one page. This is evidence about these specific responses only. It does not prove that detail/profile endpoints never contain public business contacts. The production adapters for some sources make additional offer/profile calls; those calls are deliberately absent here because the requested probe was one MCP request per source.

Quera note: an initial capture-harness argument set was rejected by local schema validation before reaching MCP because generic `limit=10` mapped to Quera's `size` field. This is not an upstream response failure. The corrected call uses only Quera's actual adapter parameters and made exactly one MCP search request.

## Per-source results

### neshan (`ns_search`)

Query: `الکترونیکی`

Status: `success`
Duration: `2584 ms`
MCP tool requests: `1`
Top-level extracted records: `10`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "limit": 10
}
````

Complete MCP response:

````json
{
  "count": 10,
  "results": [
    {
      "id": "f8cef1c36473db371f5109a9d58a6634",
      "name": "الکترونیکی پایتخت",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "نواب صفوی، دامپزشکی (محله اسکندری)",
      "lat": 35.694084,
      "lng": 51.379066,
      "distance_m": 1049,
      "rating": 4.3,
      "votes": 3
    },
    {
      "id": "3ae9a3740a92bebbb10c9feb3d357e60",
      "name": "خدمات الکترونیکی الکترون",
      "category": "تعمیرات لوازم الکترونیک",
      "address": "استان تهران، تهران، بزرگراه نواب صفوی به سمت جنوب، تقاطع  دامپزشکی، مجتمع شهاب 3، طبقه همکف",
      "lat": 35.694105,
      "lng": 51.37835,
      "distance_m": 1106,
      "rating": 5.0,
      "votes": 2,
      "phone": "02166388342"
    },
    {
      "id": "044985927c1e2fca13055514a5ee5b2c",
      "name": "تعمیرگاه بردهای الکترونیکی کمانی",
      "category": "تعمیرات لوازم الکترونیک",
      "address": "بزرگراه نواب صفوی، کمیل، خرمشهر (محله خرمشهر)",
      "lat": 35.679765,
      "lng": 51.384079,
      "distance_m": 1139,
      "rating": 3.0,
      "votes": 1,
      "phone": "09183638693"
    },
    {
      "id": "dd5c822d94a14e430231fe2fb03fc3ce",
      "name": "تعمیرات برد الکترونیکی لوازم خانگی ایمان",
      "category": "تعمیرات لوازم الکترونیک",
      "address": "امام خمینی، قصرالدشت (محله کارون شمالی)",
      "lat": 35.692621,
      "lng": 51.369843,
      "distance_m": 1771,
      "rating": 3.0,
      "votes": 1,
      "phone": "09120241680"
    },
    {
      "id": "967b658ae64cde74cec4ea60bff44b1a",
      "name": "لوازم الکترونیکی و اسپیکر کیا پلاس",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "جمهوری اسلامی، بین رازی و شیخ هادی، پاساژ یگانه، طبقه اول، پلاک ۱۱۰",
      "lat": 35.695548,
      "lng": 51.407288,
      "distance_m": 1796,
      "rating": 5.0,
      "votes": 2,
      "phone": "02166342724"
    },
    {
      "id": "9712e7113d19ba8215c67d448514a606",
      "name": "فروشگاه قطعات روشنایی و الکترونیکی الکرون",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "استان تهران، تهران،  جمهوری اسلامی، پاساژ امجد، طبقه منفی 1",
      "lat": 35.694949,
      "lng": 51.41273,
      "distance_m": 2236,
      "phone": "02146091952"
    },
    {
      "id": "e1d13f0a6e2358fc4993ce77292d3d59",
      "name": "فروشگاه الکترونیکی قرمز",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "ولیعصر، طالقانی، برادران مظفر (محله دانشگاه تهران)",
      "lat": 35.707573,
      "lng": 51.40561,
      "distance_m": 2534,
      "rating": 3.7,
      "votes": 3,
      "phone": "02188226900"
    },
    {
      "id": "aa7c325a098a8d3ab3f4f1a9a629e629",
      "name": "فروشگاه قطعات الکترونیکی ویروکیت",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "تهران، جمهوری اسلامی، بین شیروانی و فردوسی، پلاک 446، پاساژ نوین، طبقه اول، واحد 19",
      "lat": 35.69463,
      "lng": 51.418288,
      "distance_m": 2713,
      "rating": 5.0,
      "votes": 1,
      "phone": "02166722865"
    },
    {
      "id": "9309c86090f95a2999ca335a2a0488cf",
      "name": "فروش لوازم الکترونیکی (Hertz، Audison، Connection)",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "فردوسی (محله فردوسی)",
      "lat": 35.687192,
      "lng": 51.420298,
      "distance_m": 2835,
      "rating": 5.0,
      "votes": 2,
      "phone": "02166711097"
    },
    {
      "id": "c9396d5f9e335c9d0499685904c9108a",
      "name": "فروشگاه الکترونیکی تک کنار",
      "category": "فروشگاه لوازم الکترونیک",
      "address": "فردوسی، پشت شهرداری (محله فردوسی)",
      "lat": 35.686716,
      "lng": 51.421546,
      "distance_m": 2952,
      "phone": "09120150622"
    }
  ]
}
````

### balad (`bl_search`)

Query: `الکترونیکی`

Status: `success`
Duration: `1751 ms`
MCP tool requests: `1`
Top-level extracted records: `10`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "limit": 10
}
````

Complete MCP response:

````json
{
  "results": [
    {
      "type": "poi",
      "name": "قطعات الکترونیکی یاسایی",
      "id": "5XeEbb0RBgMEdb",
      "address": "تهران، نارمک شمالی، خ. جانبازان غربی",
      "lat": 35.731192,
      "lng": 51.488671,
      "phone": "02177906667"
    },
    {
      "type": "poi",
      "name": "دانشگاه آزاد اسلامی واحد الکترونیکی",
      "id": "PPu9nlQyI6KEkU",
      "address": "تهران، دروس، خ. پاسداران، خ. سوری، کوچه رام",
      "lat": 35.769342,
      "lng": 51.457418,
      "phone": "02142863000"
    },
    {
      "type": "category",
      "name": "مرکز تعمیر تجهیزات الکترونیکی",
      "category": "electronic-equipment-repair",
      "address": "نمایش نتایج مرکز تعمیر تجهیزات الکترونیکی روی نقشه"
    },
    {
      "type": "poi",
      "name": "دانشگاه آزاد اسلامی واحد الکترونیکی",
      "id": "7dyvxY2vSrc1E6",
      "address": "تهران، دروس، خ. پاسداران، کوچه نیستان نهم",
      "lat": 35.769255,
      "lng": 51.45772
    },
    {
      "type": "poi",
      "name": "دفتر پابند الکترونیکی کانون اصلاح و تربیت",
      "id": "Pvsvia5xs34OUU",
      "address": "تهران، شهر زیبا، خ. دکتر شریعتی، ب. شهید همت، خ. اردوشاهی",
      "lat": 35.750948,
      "lng": 51.291202,
      "phone": "02144329692"
    },
    {
      "type": "poi",
      "name": "دفتر خدمات الکترونیکی قضایی",
      "id": "5iS0hJbJQZwAD3",
      "address": "تهران، نیلوفر، خ. سهروردی شمالی، بلوار خرمشهر",
      "lat": 35.735643,
      "lng": 51.437889,
      "phone": "02188761002"
    },
    {
      "type": "poi",
      "name": "شرکت مدیریت امن الکترونیکی کاشف",
      "id": "5cOEmrGapMu1f1",
      "address": "تهران، زرگنده، خ. دستگردی",
      "lat": 35.765265,
      "lng": 51.439022,
      "phone": "02172861000"
    },
    {
      "type": "poi",
      "name": "دفترخدماتی الکترونیکی ساتا نیروهای مسلح",
      "id": "3US1GC6bevpC00",
      "address": "اندیشه، اندیشه فاز سه، بلوار آزادی، کوچه سنایی",
      "lat": 35.698499,
      "lng": 51.030571
    },
    {
      "type": "poi",
      "name": "دانشگاه آزاد اسلامی واحد الکترونیکی",
      "id": "3cDSQcnK2DSh38",
      "address": "تهران، شهرک غرب، خ. ایران زمین، خ. مهستان",
      "lat": 35.760287,
      "lng": 51.378054,
      "phone": "02142863000"
    },
    {
      "type": "poi",
      "name": "دفتر خدمات الکترونیکی ساتا",
      "id": "5MlNby5ov6sNzj",
      "address": "تهران، حکیمیه، خ. لاله",
      "lat": 35.74383,
      "lng": 51.599253,
      "phone": "02177316808"
    }
  ]
}
````

### emalls (`em_search`)

Query: `الکترونیکی`

Status: `success`
Duration: `2905 ms`
MCP tool requests: `1`
Top-level extracted records: `10`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "page": 1,
  "limit": 10
}
````

Complete MCP response:

````json
{
  "heading": "همه محصولات شامل الکترونیکی امروز (۲۹ آبان)",
  "page": 1,
  "has_next": true,
  "count": 10,
  "products": [
    {
      "id": 26130756,
      "title": "تلویزیون ال ای دی 65 اینچ سام الکترونیک مدل QA65Q80D",
      "price": 135000000,
      "price_max": 175900000,
      "shops": 6,
      "updated": "2 سال و 6 ماه و 21 روز و 9 ساعت پیش"
    },
    {
      "id": 8326271,
      "title": "ماشین لباسشویی سام الکترونیک مدل DD-P1485 ظرفیت 9 کیلوگرم",
      "price": 100700000,
      "price_max": 154146000,
      "shops": 11,
      "updated": "3 سال و 6 ماه و 25 روز و 17 ساعت پیش"
    },
    {
      "id": 4899579,
      "title": "کابل برق افشان 2 در 1.5 (1.5×2) البرز الکتریک نور (لینکو)",
      "price": 10451138,
      "price_max": 10451138,
      "shops": 1,
      "updated": "3 سال و 6 ماه و 25 روز و 17 ساعت پیش"
    },
    {
      "id": 842418,
      "title": "ترازوی آشپزخانه الکترونیک مدل SF 400",
      "price": 465000,
      "price_max": 11000000,
      "shops": 154,
      "updated": "3 سال و 6 ماه و 25 روز و 17 ساعت پیش"
    },
    {
      "id": 986210,
      "title": "سه راه صنعتی پارت الکتریک",
      "price": 466000,
      "price_max": 863000,
      "shops": 20,
      "updated": "3 سال و 6 ماه و 25 روز و 17 ساعت پیش"
    },
    {
      "id": 2321225,
      "title": "اینورتر جوشکاری 250 آمپر صبا الکتریک مدل RINV-250-V",
      "price": 39450000,
      "price_max": 84000000,
      "shops": 18,
      "updated": "4 ماه و 12 روز و 22 ساعت پیش"
    },
    {
      "id": 13630996,
      "title": "دستگاه فشار سنج الکترونیکی بازویی دیجیتالی ارم استایل Electronic Blood",
      "price": 999000,
      "price_max": 2722500,
      "shops": 32,
      "updated": "10 روز و 20 ساعت پیش"
    },
    {
      "id": 26007897,
      "title": "فندک مدل الکتریکی شارژی",
      "price": 270000,
      "price_max": 4426380,
      "shops": 21,
      "updated": "1 ماه و 12 روز و 20 ساعت پیش"
    },
    {
      "id": 4912786,
      "title": "کابل برق افشان 2 در 4 (4×2) البرز الکتریک نور (لینکو) کلاف 100 متری",
      "price": 25955230,
      "price_max": 25955230,
      "shops": 1,
      "updated": "12 روز و 19 ساعت پیش"
    },
    {
      "id": 25075490,
      "title": "اینورتر جوشکاری 200 آمپر صبا الکتریک مدل COMFORT SERIES R201",
      "price": 19900000,
      "price_max": 50371200,
      "shops": 45,
      "updated": "6 ماه و 19 روز و 10 ساعت پیش"
    }
  ]
}
````

### basalam (`bs_search`)

Query: `الکترونیکی`

Status: `success`
Duration: `1466 ms`
MCP tool requests: `1`
Top-level extracted records: `10`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "page": 1,
  "limit": 10
}
````

Complete MCP response:

````json
{
  "total": 2066,
  "page": 1,
  "products": [
    {
      "id": 44024651,
      "name": "دستگاه فشار سنج الکترونیکی دیجیتالی ارم استایل سخنگو فارسی",
      "price": 1130000,
      "rating": 4.6,
      "rating_count": 60,
      "in_stock": true,
      "stock": 4,
      "category": "ابزار های پزشکی",
      "shop": "گریش مال",
      "shop_id": "gerishmall"
    },
    {
      "id": 58391275,
      "name": "فایل کریستالی 10 طبقه 50 کشو / جعبه ابزار قطعات الکترونیکی / اورگانایزر",
      "price": 1598900,
      "rating": 4.8,
      "rating_count": 9,
      "in_stock": true,
      "stock": 980,
      "category": "جعبه و کیف ابزار",
      "shop": "ابزاردار",
      "shop_id": "abzardar"
    },
    {
      "id": 30773756,
      "name": "کیت آموزش 200 مدار الکترونیکی با برد بورد - جهت دریافت تخفیف خرید عمده پیام دهید",
      "price": 966000,
      "rating": 4.8,
      "rating_count": 15,
      "in_stock": true,
      "stock": 3,
      "category": "لباس ورزشی مردانه و پسرانه",
      "shop": "بازرگانی فراذهن",
      "shop_id": "farazehn-net"
    },
    {
      "id": 56694241,
      "name": "قاب تستر قطعات الکترونیکی مدل LCR-T4",
      "price": 599000,
      "rating": 4.7,
      "rating_count": 4,
      "in_stock": true,
      "stock": 32,
      "category": "قطعات الکترونیکی",
      "shop": "FRACTRONIX",
      "shop_id": "fractronix"
    },
    {
      "id": 17337778,
      "name": "دستگاه فشار سنج الکترونیکی دیجیتالی ارم استایل Electronic Blood ",
      "price": 1239000,
      "rating": 4.2,
      "rating_count": 105,
      "in_stock": true,
      "stock": 8,
      "category": "ابزار های پزشکی",
      "shop": "لوازم خانگی برتر1",
      "shop_id": "khaneebartaar"
    },
    {
      "id": 16826798,
      "name": "دستگاه فشار سنج الکترونیکی دیجیتالی ارم استایل Electronic Blood",
      "price": 1241000,
      "rating": 4.2,
      "rating_count": 353,
      "in_stock": true,
      "stock": 25,
      "category": "ابزار های پزشکی",
      "shop": "لوازم خانگی برتر1",
      "shop_id": "khaneebartaar"
    },
    {
      "id": 24094046,
      "name": "جایگزین باطری موتور سیکلت الکترونیکی ",
      "price": 411100,
      "rating": 3.9,
      "rating_count": 22,
      "in_stock": true,
      "stock": 70,
      "category": "باتری موتور سیکلت",
      "shop": "موتور سیکلت برغمدی",
      "shop_id": "motor_barghamadi"
    },
    {
      "id": 45136896,
      "name": "کابل شارژر پابند الکترونیکی مدل b (پابند الکترونیکی زندان)",
      "price": 799000,
      "rating": 5,
      "rating_count": 4,
      "in_stock": true,
      "stock": 994,
      "category": "سایر کابل و تبدیل",
      "shop": "شیخی شاپ",
      "shop_id": "sheykhi_watch"
    },
    {
      "id": 57854304,
      "name": "ست انبرآلات الکترونیکی 5 عددی فرد",
      "price": 1146600,
      "original_price": 1274000,
      "discount_pct": 10,
      "rating": 5,
      "rating_count": 1,
      "in_stock": true,
      "stock": 7,
      "category": "انبر",
      "shop": "فروشگاه ابزار ایران صنعت حامد معزز",
      "shop_id": "iransanattools"
    },
    {
      "id": 26609593,
      "name": "دستگاه فشارسنج الکترونیکی دیجیتالی ارم استایل Electronic Blood همراه با سیم شارژر ",
      "price": 1298000,
      "rating": 3.9,
      "rating_count": 24,
      "in_stock": true,
      "stock": 15,
      "category": "محافظ طبی",
      "shop": "لوازم خانگی برتر1",
      "shop_id": "khaneebartaar"
    }
  ]
}
````

### rasmio (`rs_search_companies`)

Query: `الکترونیکی`

Status: `success`
Duration: `6555 ms`
MCP tool requests: `1`
Top-level extracted records: `10`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "page": 1,
  "page_size": 10
}
````

Complete MCP response:

````json
{
  "total": 977,
  "page": 1,
  "pages": 98,
  "results": [
    {
      "kind": "company",
      "company_id": "10320773527",
      "name": "توسعه خدمات الکترونیکی آدونیس",
      "summary": "15 سال • +هزار میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "محمدرضا اسکندری",
      "licenses": [
        "فعالیت خدمات فنی نصب و پشتیبانی محصولات افتا",
        "تولید دستگاه خودکار خدمات بانکی - پرداخت/دریافت",
        "مجوز فعالیت در حوزه فناوری اطلاعات و ارتباطات (شخص حقوقی)",
        "انفورماتیک سیستم‌های ویژه",
        "دانش بنیان نوآور در حوزه فناوری اطلاعات و ارتباطات و نرم‌افزارهای رایانه‌ای"
      ],
      "license_count": 5,
      "top_products": [
        "دستگاه خودپرداز، سالنی، نمایشگر 15 in، LCD لمسی، EASTCOM، مدل 285، چین، نوع بارکد خوان 2D",
        "دستگاه خودپرداز، سالنی، نمایشگر 15 in، LCD معمولی، YIHUA، مدل ATM 6060، چین، نوع بارکد خوان 1D"
      ],
      "top_categories": [
        "تولیدی و صنعتی و فروشگاهی",
        "کالای دیجیتال",
        "کاغذ، هنر و لوازم تحریر"
      ]
    },
    {
      "kind": "company",
      "company_id": "10103025726",
      "name": "صنایع الکترونیکی مگا مداوم",
      "summary": "21 سال • +هزار میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "محمد حسین رضائیان",
      "licenses": [
        "تولید یو پی اس سه فاز",
        "پروانه کسب تولید و تعمیر انواع دستگاههای ترانسفورماتور موتور های کاهنده و افزاینده",
        "انفورماتیک خدمات پشتیبانی",
        "دانش بنیان نوآور در حوزه برق و الکترونیک، فوتونیک، مخابرات و سیستمهای خودکار"
      ],
      "license_count": 4,
      "top_products": [
        "ترانسفورماتور، اندازه گیری و حفاظت، 3 kVA، کاهنده و افزاینده، تک فاز، مدل DEFENDER WM، چین، ولتاژ اولیه 220 V، ولتاژ ثان",
        "UPS، برخط، 3 فاز، به 3 فاز، 20 kVA، مدل Pyramid DSPT 20kva، ترکیه، 54 عدد، ولتاژ ورودی 380 V، ولتاژ خروجی 380 V، جریان و"
      ],
      "top_categories": [
        "برق، الکترونیک و مخابرات",
        "کالای دیجیتال",
        "تولیدی و صنعتی و فروشگاهی"
      ]
    },
    {
      "kind": "company",
      "company_id": "10103480855",
      "name": "صنایع الکترونیکی صوت ماستر",
      "summary": "20 سال • +هزار میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "امیر ماستری فراهانی",
      "licenses": [
        "پروانه کسب تولید مصنوعات فلزی (مسی، برنجی، برنزی، استیل و ...)",
        "تشخیص صلاحیت شرکت های دانش بنیان",
        "دانش بنیان نوآور در حوزه مواد پیشرفته و محصولات مبتنی بر فناوری‌های شیمیایی"
      ],
      "license_count": 3,
      "top_products": [
        "باند، MASTER AUDIO، مدل پژو پارس-چپ، شکل دایره ای، سایز 6 in، توان خروجی صدا 70 W، بسته بندی کارتن 12 عددی",
        "تیوتر، منفرد، قطعات بلندگو تویتر مدل TW25-03G، سازنده SHENGZHOU BEITE IMPORT AND EXPORT، چین، شماره فنی 1721165021"
      ],
      "top_categories": [
        "حمل‌ونقل و لجستیک",
        "ملزومات خدمات و صنایع",
        "ابزارآلات"
      ]
    },
    {
      "kind": "company",
      "company_id": "10630140877",
      "name": "الکترونیکی بردهای هوشمند ایرانیان",
      "summary": "20 سال • +10 میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "سید احمد سیف الحسینی",
      "licenses": [
        "مجوز فعالیت در حوزه فناوری اطلاعات و ارتباطات (شخص حقوقی)",
        "تشخیص صلاحیت شرکت های دانش بنیان",
        "فعالیت خدمات عملیاتی آزمون و ارزیابی امنیتی افتا",
        "انفورماتیک سیستم‌های ویژه",
        "دانش بنیان نوآور در حوزه برق و الکترونیک، فوتونیک، مخابرات و سیستمهای خودکار"
      ],
      "license_count": 5,
      "top_products": [
        "دستگاه فتوکپی، لیزری، رومیزی، تک رنگ، CANON، مدل 2206n، کره جنوبی، قابلیت پرینت دارد، قابلیت اسکن دارد",
        "دستگاه، 3 کاره، لیزری، سیاه و سفید، CANON، مدل IR2206N، کره جنوبی، سایز کاغذ A3 \\ A4"
      ],
      "top_categories": [
        "ابزارآلات",
        "کالای دیجیتال"
      ]
    },
    {
      "kind": "company",
      "company_id": "14006592448",
      "name": "فناوران هویت الکترونیکی امن",
      "summary": "10 سال • +10 میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "مهدی ناظمیان",
      "licenses": [
        "مجوز فعالیت در حوزه فناوری اطلاعات و ارتباطات (شخص حقوقی)",
        "فعالیت خدمات عملیاتی امن سازی و مقاوم سازی سامانه ها، زیرساخت ها و سرویس ها افتا",
        "فعالیت خدمات عملیاتی امنیت فضای تولید و تبادل اطلاعات",
        "اینماد",
        "انفورماتیک امنیت فضای تولید و تبادل اطلاعات"
      ],
      "license_count": 6
    },
    {
      "kind": "company",
      "company_id": "10320718470",
      "name": "شبکه الکترونیکی پرداخت کارت شاپرک",
      "summary": "15 سال • +هزار میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "محمدصادق محبوبی",
      "licenses": [
        "گواهی ایمنی آسانسور (ادواری)",
        "انفورماتیک سیستم‌های ویژه",
        "دانش بنیان نوآور در حوزه فناوری اطلاعات و ارتباطات و نرم‌افزارهای رایانه‌ای"
      ],
      "license_count": 3
    },
    {
      "kind": "company",
      "company_id": "14003937668",
      "name": "مدیریت امن الکترونیکی کاشف",
      "summary": "13 سال • +هزار میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "وحید خدابخشی",
      "licenses": [
        "فعالیت خدمات فنی امنیت فضای تولید و تبادل اطلاعات",
        "مجوز فعالیت در حوزه فناوری اطلاعات و ارتباطات (شخص حقوقی)",
        "اینماد",
        "دانش بنیان نوآور در حوزه فناوری اطلاعات و ارتباطات و نرم‌افزارهای رایانه‌ای"
      ],
      "license_count": 4
    },
    {
      "kind": "company",
      "company_id": "14004555553",
      "name": "سلامت الکترونیکی تامین",
      "summary": "13 سال • +1 میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "اشکان جمشیدوند",
      "licenses": [
        "بهره‌برداری تولید نرم افزار",
        "مجوز فعالیت در حوزه فناوری اطلاعات و ارتباطات (شخص حقوقی)",
        "گواهی فنی محصولات نرم افزاری",
        "انفورماتیک سیستم‌های ویژه",
        "دانش بنیان فناور در حوزه فناوری اطلاعات و ارتباطات و نرم‌افزارهای رایانه‌ای"
      ],
      "license_count": 5
    },
    {
      "kind": "company",
      "company_id": "10200127412",
      "name": "الکترونیکی سهند کیوان",
      "summary": "33 سال • +1 میلیارد ریال سرمایه ثبتی • شرکت دانش بنیان",
      "ceo": "کیوان قاسم بگلو",
      "licenses": [
        "تولید ساخت تونل پاشش مایعات",
        "فعالیت تحقیق و توسعه واحدهای تولیدی، تجاری و خدماتی",
        "دانش بنیان نوآور در حوزه برق و الکترونیک، فوتونیک، مخابرات و سیستمهای خودکار"
      ],
      "license_count": 3,
      "top_products": [
        "رک، ایستاده، برند سهند کیوان، مدل BC100، سازنده الکترونیکی سهند کیوان، ایران، تعداد یونیت داخلی 32، تعداد جایگاه فن 1",
        "رک، ایستاده، برند سهند کیوان، مدل BC50، سازنده الکترونیکی سهند کیوان، ایران، تعداد یونیت داخلی 32، تعداد جایگاه فن 1"
      ],
      "top_categories": [
        "برق، الکترونیک و مخابرات",
        "کالای دیجیتال"
      ]
    },
    {
      "kind": "company",
      "company_id": "10102072317",
      "name": "مخابراتی و الکترونیکی موج نصر گستر",
      "summary": "27 سال • +1 میلیارد ریال سرمایه ثبتی",
      "ceo": "پرویز جوادی"
    }
  ]
}
````

### torob (`tb_find_shops`)

Query: `الکترونیکی`

Status: `success`
Duration: `3054 ms`
MCP tool requests: `1`
Top-level extracted records: `10`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "page": 0,
  "limit": 10,
  "kind": "all"
}
````

Complete MCP response:

````json
{
  "query": "الکترونیکی",
  "count": 24,
  "next_page": 1,
  "shops": [
    {
      "id": 371674,
      "name": "الکترونیکی جلالی",
      "city": "کرج",
      "domain": "jalalielectronic.ir",
      "url": "https://torob.com/shop/371674"
    },
    {
      "id": 30941,
      "name": "کافه قطعات الکترونیکی",
      "city": "شیراز",
      "domain": "cafeelec.ir",
      "url": "https://torob.com/shop/30941"
    },
    {
      "id": 324642,
      "name": "تجهیزات الکترونیکی پرداخت ایران",
      "city": "تبریز",
      "domain": "tepiran.ir",
      "url": "https://torob.com/shop/324642"
    },
    {
      "id": 391414,
      "name": "گنجه الکترونیکی",
      "city": "رشت",
      "domain": "eganje.com",
      "url": "https://torob.com/shop/391414"
    },
    {
      "id": 261841,
      "name": "خانه الکترونیکی تهران",
      "city": "تهران",
      "domain": "d92ce523-b33c-4648-a7f5-6c4c0a8c327d.offline-shop.torob.ir",
      "url": "https://torob.com/shop/261841"
    },
    {
      "id": 229470,
      "name": "پرشین الکترونیکی",
      "city": "مشهد",
      "domain": "46699063-d76b-4127-b24f-53c94602447e.offline-shop.torob.ir",
      "url": "https://torob.com/shop/229470"
    },
    {
      "id": 104239,
      "name": "قطعات الکترونیکی",
      "city": "شهریار",
      "domain": "electronickit1.com",
      "url": "https://torob.com/shop/104239"
    },
    {
      "id": 538805,
      "name": "تولید تجهیزات الکترونیکی سراما",
      "city": "بیرجند",
      "domain": "serama.ir",
      "url": "https://torob.com/shop/538805"
    },
    {
      "id": 536008,
      "name": "لوازم الکترونیکی مغناطیس",
      "city": "اصفهان",
      "domain": "6a87747a-7a22-46a9-b93f-934a83584a6e.offline-shop.torob.ir",
      "url": "https://torob.com/shop/536008"
    },
    {
      "id": 533711,
      "name": "قطعات الکترونیکی بابا برقی",
      "city": "رباط کریم",
      "domain": "df42da5d-a982-44ba-a998-9663331ad45d.offline-shop.torob.ir",
      "url": "https://torob.com/shop/533711"
    }
  ]
}
````

### iran_jobs (`job_companies`)

Query: `الکترونیکی`

Status: `success`
Duration: `3093 ms`
MCP tool requests: `1`
Companies in source-specific arrays: `29` (11 IranTalent, 8 Jobinja, 10 Jobvision); the response groups results by site rather than in a flat array.

Arguments sent:

````json
{
  "name": "الکترونیکی",
  "page": 1,
  "site": "all"
}
````

Complete MCP response:

````json
{
  "irantalent": {
    "total": 11,
    "page": 1,
    "pages": 1,
    "companies": [
      {
        "id": "a1ec2cb3-8aa7-4c8f-9dd6-49c3fcf20a92",
        "name": "Adonis Tech (Adonis ESD Co)",
        "name_fa": "توسعه خدمات الکترونیکی آدونیس",
        "slug": "adonis-tech-adonis-esd-co",
        "ratings_count": 12,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/adonis-tech-adonis-esd-co/a1ec2cb3-8aa7-4c8f-9dd6-49c3fcf20a92/overview"
      },
      {
        "id": "4b07485d-bd8f-42d8-8c4d-17136fa171ec",
        "name": "Mega Modavem",
        "name_fa": "صنایع الکترونیکی مگا مداوم",
        "slug": "mega-modavem",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/mega-modavem/4b07485d-bd8f-42d8-8c4d-17136fa171ec/overview"
      },
      {
        "id": "33cf252b-7e64-42f1-8823-7e63e18fc5cf",
        "name": "Electronic services office of the city",
        "name_fa": "دفتر خدمات الکترونیکی شهر",
        "slug": "electronic-services-office-of-the-city",
        "ratings_count": 4,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/electronic-services-office-of-the-city/33cf252b-7e64-42f1-8823-7e63e18fc5cf/overview"
      },
      {
        "id": "26115b76-880d-4fa3-8547-7028515324c4",
        "name": "Parnian Telecommunication and Electronic Database Company",
        "name_fa": "شرکت مخابرات الکترونیک و شرکت پایگاه‌داده‌های الکترونیکی",
        "slug": "parnian-telecommunication-and-electronic-database-company",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/parnian-telecommunication-and-electronic-database-company/26115b76-880d-4fa3-8547-7028515324c4/overview"
      },
      {
        "id": "04c31446-b647-4bd0-987a-eb7170e21b7e",
        "name": "Iranian e - Institute of Higher Education",
        "name_fa": "موسسه آموزش عالی الکترونیکی ایرانیان",
        "slug": "iranian-e-institute-of-higher-education",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/iranian-e-institute-of-higher-education/04c31446-b647-4bd0-987a-eb7170e21b7e/overview"
      },
      {
        "id": "ec4ba096-13c7-419b-b145-31ab9cfe2f46",
        "name": "Iran Electronic Industries",
        "name_fa": "صنایع الکترونیکی ایران‌",
        "slug": "iran-electronic-industries",
        "ratings_count": 2,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/iran-electronic-industries/ec4ba096-13c7-419b-b145-31ab9cfe2f46/overview"
      },
      {
        "id": "ea17eae1-b6e0-4b8e-8b4d-1bcfa072d8aa",
        "name": "Parsian ecommerce",
        "name_fa": "تجارت الکترونیکی پارسی",
        "slug": "parsian-ecommerce",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/parsian-ecommerce/ea17eae1-b6e0-4b8e-8b4d-1bcfa072d8aa/overview"
      },
      {
        "id": "d3f28e76-9f82-4037-a8d9-b5e6c52bb519",
        "name": "iranian net",
        "name_fa": "شرکت خدمات ارتباطی و الکترونیکی ایرانیان نت",
        "slug": "iranian-net",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/iranian-net/d3f28e76-9f82-4037-a8d9-b5e6c52bb519/overview"
      },
      {
        "id": "a8a0eb19-2a4a-4163-a67f-6a7848e30028",
        "name": "Salamat Electronic Tamin",
        "name_fa": "سلامت الکترونیکی تامین",
        "slug": "salamat-electronic-tamin",
        "ratings_count": 0,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/salamat-electronic-tamin/a8a0eb19-2a4a-4163-a67f-6a7848e30028/overview"
      },
      {
        "id": "085132ec-4a27-4097-86ff-936c4d8657ed",
        "name": "Bahram Electronic",
        "name_fa": "بهرام الکترونیکی",
        "slug": "bahram-electronic",
        "ratings_count": 1,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/bahram-electronic/085132ec-4a27-4097-86ff-936c4d8657ed/overview"
      },
      {
        "id": "f83adbc4-045f-46d4-837c-f631ba9b3ee1",
        "name": "Rahtab",
        "name_fa": "راهکار هوشمندانه تنظیم الکترونیکی بازار بیستون",
        "slug": "rahtab",
        "ratings_count": 0,
        "open_jobs": 0,
        "url": "https://www.irantalent.com/company/rahtab/f83adbc4-045f-46d4-837c-f631ba9b3ee1/overview"
      }
    ]
  },
  "jobinja": {
    "page": 1,
    "companies": [
      {
        "slug": "hovita-3",
        "name": "فناوران هویت الکترونیکی امن (هویتا)",
        "name_en": "Hovita",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت",
        "hiring": true
      },
      {
        "slug": "adonis-electronic-services-development-co",
        "name": "توسعه خدمات الکترونیکی آدونیس",
        "name_en": "Adonis Electronic Services Development Co.",
        "city": "تهران، تهران",
        "industry": "بانکداری",
        "hiring": true
      },
      {
        "slug": "megamodavem",
        "name": "صنایع الکترونیکی مگا مداوم",
        "name_en": "Mega Modavem",
        "city": "تهران، تهران",
        "industry": "واردات و صادرات",
        "hiring": true
      },
      {
        "slug": "stareh",
        "name": "شرکت مهندسی تجهیزات الکترونیکی استاره",
        "name_en": "Stareh",
        "industry": "خدمات درمانی، پزشکی و سلامت"
      },
      {
        "slug": "sawissmarjan",
        "name": "تجارت الکترونیکی فناوران ساویس مرجان",
        "name_en": "SAWISSMARJAN",
        "city": "تهران، تهران",
        "industry": "خرده‌فروشی، عمده‌فروشی و فروشگاه‌های زنجیره‌ای"
      },
      {
        "slug": "atma",
        "name": "تولید محتوای الکترونیکی آتما",
        "name_en": "Atma",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت"
      },
      {
        "slug": "voltaje",
        "name": "الکترونیکی ولتاژ",
        "name_en": "Voltaje",
        "industry": "کامپیوتر، فناوری اطلاعات و اینترنت"
      },
      {
        "slug": "sawiss-marjan-ecommerce-co",
        "name": "تجارت الکترونیکی فناوران ساویس مرجان",
        "name_en": "Sawiss Marjan Ecommerce Co",
        "industry": "سرمایه‌گذاری و تحلیل کسب‌وکار"
      }
    ],
    "next": "Raise page for more."
  },
  "jobvision": {
    "total": 32,
    "page": 1,
    "companies": [
      {
        "id": 4076,
        "name": "توسعه خدمات الکترونیکی آدونیس",
        "name_en": "Adonis",
        "open_ads": 10,
        "rating": 3.53,
        "rank": 526,
        "url": "https://jobvision.ir/companies/4076"
      },
      {
        "id": 698,
        "name": "مجله الکترونیکی قاب",
        "name_en": "Ghaab Mag",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/698"
      },
      {
        "id": 2628,
        "name": "شرکت الکترونیکی بردهای هوشمند ایرانیان",
        "name_en": "IBECo",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/2628"
      },
      {
        "id": 3189,
        "name": "مدیریت امن الکترونیکی کاشف",
        "name_en": "Kashef Banking Information Security",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/3189"
      },
      {
        "id": 3896,
        "name": "شرکت سلامت الکترونیکی تامین (ساتا)",
        "name_en": "satahealth",
        "open_ads": 2,
        "url": "https://jobvision.ir/companies/3896"
      },
      {
        "id": 4135,
        "name": "شرکت صنایع الکترونیکی مگامداوم",
        "name_en": "MEGA MODAVEM",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/4135"
      },
      {
        "id": 4927,
        "name": "فناوران هویت الکترونیکی امن(هویتا)",
        "name_en": "Fanavarane Hoviate Electronici Amn",
        "open_ads": 2,
        "url": "https://jobvision.ir/companies/4927"
      },
      {
        "id": 5358,
        "name": "نوآوران توسعه تجارت الکترونیکی پایا (تتا)",
        "name_en": "Teta Corp",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/5358"
      },
      {
        "id": 8306,
        "name": "موسسه آموزش عالی الکترونیکی ایرانیان (وزارت علوم)",
        "name_en": "Iranians University",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/8306"
      },
      {
        "id": 9537,
        "name": "واحد الکترونیکی دانشگاه آزاد",
        "name_en": "iauec",
        "open_ads": 0,
        "url": "https://jobvision.ir/companies/9537"
      }
    ]
  }
}
````

### quera (`qr_companies`)

The first capture-harness attempt was rejected by local JSON-schema validation before an MCP request: a generic `limit=10` was incorrectly mapped to Quera's company-size field. The application adapter does not send that generic limit. Corrected request below sends only the fields used by the Quera adapter; exactly one external MCP search call was made.

Status: `success`
Duration: `4998 ms`
MCP tool requests: `1`
Top-level extracted records: `3`

Arguments sent:

````json
{
  "search": "الکترونیکی",
  "page": 1
}
````

Complete MCP response:

````json
{
  "total": 3,
  "page": 1,
  "has_more": false,
  "results": [
    {
      "slug": "sharif",
      "name": "مرکز آموزشهای الکترونیکی دانشگاه صنعتی شریف",
      "tagline": "مرکز آموزش های الکترونیکی دانشگاه شریف",
      "city": "تهران",
      "size": "1-10",
      "open_jobs": 0,
      "technologies": [
        "JavaScript",
        "PHP",
        "MySQL",
        "AngularJS"
      ],
      "url": "https://quera.org/magnet/companies/sharif"
    },
    {
      "slug": "iauec",
      "name": "واحد الکترونیکی دانشگاه آزاد اسلامی",
      "tagline": "واحد الکترونیکی دانشگاه آزاد اسلامی",
      "city": "تهران",
      "size": "201-500",
      "open_jobs": 0,
      "technologies": [
        "C#",
        "SQL",
        ".NET"
      ],
      "url": "https://quera.org/magnet/companies/iauec"
    },
    {
      "slug": "iau",
      "name": "دانشگاه آزاد اسلامی واحد الکترونیکی",
      "tagline": "واحد الکترونیکی دانشگاه آزاد اولین و بزرگترین دانشگاه مجازی کشور",
      "city": "تهران",
      "size": "51-200",
      "open_jobs": 0,
      "technologies": [
        "Java",
        "C#",
        "jQuery",
        "CSS",
        "SQL",
        "ASP.NET",
        "ASP.NET MVC",
        ".NET Core"
      ],
      "url": "https://quera.org/magnet/companies/iau"
    }
  ]
}
````
### digikala (`dk_search`)

Query: `الکترونیکی`

Status: `success`
Duration: `1725 ms`
MCP tool requests: `1`
Top-level extracted records: `22`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "page": 1
}
````

Complete MCP response:

````json
{
  "total": 975,
  "page": 1,
  "total_pages": 49,
  "products": [
    {
      "id": 23312124,
      "title": "سنسور دمای صنعتی وستا مدل PT500 طول 2.5 متر و محدوده دمایی منفی 50 تا 200 درجه",
      "brand": "متفرقه",
      "price": 7500000,
      "in_stock": true,
      "seller": "بروز تجهیز",
      "image": "https://dkstatics-public.digikala.com/digikala-products/87cf169135f73aa0bc2b36e43a34538e37b724ae_1795084719.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-23312124/",
      "match": "none"
    },
    {
      "id": 1678712,
      "title": "کیت آموزش الکترونیک مهندسیکا مدل STK00127 ",
      "brand": "مهندسیکا",
      "price": 9917000,
      "price_before_discount": 10550000,
      "discount_pct": 6,
      "in_stock": true,
      "seller": "مهندسیکالا",
      "rating": 4.5,
      "rating_count": 2,
      "image": "https://dkstatics-public.digikala.com/digikala-products/111687073.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-1678712/",
      "match": "none"
    },
    {
      "id": 21516353,
      "title": "راکت بازرسی فلزیاب مدل super scanner",
      "brand": "متفرقه",
      "price": 6840000,
      "price_before_discount": 7600000,
      "discount_pct": 10,
      "in_stock": true,
      "seller": "پرواستور ایران",
      "rating": 4.8,
      "rating_count": 5,
      "image": "https://dkstatics-public.digikala.com/digikala-products/e902bdf814e42743c93f15624f0d08f7d6dc058b_1771843201.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-21516353/",
      "match": "none"
    },
    {
      "id": 3137049,
      "title": "کیت آموزشی نوآوران الکترونیک مدل NMP201 کد G715",
      "brand": "متفرقه",
      "price": 9100000,
      "in_stock": true,
      "seller": "فرآیند کیت",
      "rating": 5.0,
      "rating_count": 1,
      "image": "https://dkstatics-public.digikala.com/digikala-products/1d578a7e77228a10c830d767e3cb42cd5e8b2cf4_1595865285.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-3137049/",
      "match": "none"
    },
    {
      "id": 10882850,
      "title": "کیت آموزشی ربوکارنا مدل الکترونیک پیشرفته",
      "brand": "رساکو",
      "price": 1599990,
      "in_stock": true,
      "seller": "وحید کیت",
      "rating": 4.3,
      "rating_count": 32,
      "image": "https://dkstatics-public.digikala.com/digikala-products/cac97539aca9e6f79c5722b3724950c98f5dd753_1678707496.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-10882850/",
      "match": "none"
    },
    {
      "id": 9257598,
      "title": "کیت آموزشی مدل آموزش الکترونیک",
      "brand": "متفرقه",
      "price": 1999990,
      "in_stock": true,
      "seller": "وحید کیت",
      "rating": 2.5,
      "rating_count": 2,
      "image": "https://dkstatics-public.digikala.com/digikala-products/471e677fd297d5ce87cc7d43eddbe656757c7db6_1661156852.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-9257598/",
      "match": "none"
    },
    {
      "id": 760698,
      "title": "کیت سرگرمی الکترونیک چهار پروژه در یک آردوینو برند مهندسیکا AD00126-4 in 1 ",
      "brand": "متفرقه",
      "price": 8414880,
      "price_before_discount": 8952000,
      "discount_pct": 6,
      "in_stock": true,
      "seller": "مهندسیکالا",
      "rating": 4.3,
      "rating_count": 7,
      "image": "https://dkstatics-public.digikala.com/digikala-products/3444550.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-760698/",
      "match": "none"
    },
    {
      "id": 9170951,
      "title": "کیت آموزشی الکترونیک مدل مقدماتی ربوکارنا",
      "brand": "متفرقه",
      "price": 1669990,
      "in_stock": true,
      "seller": "تولیدی آلفا",
      "rating": 3.2,
      "rating_count": 11,
      "image": "https://dkstatics-public.digikala.com/digikala-products/0c802ceb8f60236e9fd69d30805695af8a3c21d3_1660247362.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-9170951/",
      "match": "none"
    },
    {
      "id": 5729470,
      "title": "کیت آموزشی مدار الکتریکی مدل 2000G",
      "brand": "متفرقه",
      "price": 259420,
      "in_stock": true,
      "seller": "مداد فروش",
      "rating": 4.0,
      "rating_count": 72,
      "image": "https://dkstatics-public.digikala.com/digikala-products/ba0dcfc8f7a662db8d62eac1e3903e8c10c2ae47_1626025538.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-5729470/",
      "match": "none"
    },
    {
      "id": 14415916,
      "title": "کیت آموزش الکترونیک مهندسیکا مدل 55 پروژه جامع دانش آموزی DIY+55",
      "brand": "مهندسیکا",
      "price": 16966050,
      "price_before_discount": 17859000,
      "discount_pct": 5,
      "in_stock": true,
      "seller": "مهندسیکالا",
      "rating": 1.0,
      "rating_count": 1,
      "image": "https://dkstatics-public.digikala.com/digikala-products/c5fd1d5a7672209ab6dd2904bb5e249fb3ecc5ff_1707922375.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-14415916/",
      "match": "none"
    },
    {
      "id": 4388059,
      "title": "کیت آموزشی الکترونیکی مدل MSP",
      "brand": "متفرقه",
      "price": 223890,
      "in_stock": true,
      "seller": "وحید کیت",
      "rating": 3.9,
      "rating_count": 131,
      "image": "https://dkstatics-public.digikala.com/digikala-products/61d4c6585d6eca268342e21c18014abb1b554f84_1612371670.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-4388059/",
      "match": "all"
    },
    {
      "id": 5729474,
      "title": "کیت آموزشی مدار الکتریکی مدل 2000G",
      "brand": "متفرقه",
      "price": 210000,
      "in_stock": true,
      "seller": "تحریر هلیا",
      "rating": 3.6,
      "rating_count": 70,
      "image": "https://dkstatics-public.digikala.com/digikala-products/5351a0cab3b25346792bb5a28b219f29846943f3_1626106212.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-5729474/",
      "match": "none"
    },
    {
      "id": 21936908,
      "title": "کیت آموزش الکترونیک مهندسیکا مدل پروژه دانش آموزی کد KIT_99DIY",
      "brand": "مهندسیکا",
      "price": 20352880,
      "price_before_discount": 21652000,
      "discount_pct": 6,
      "in_stock": true,
      "seller": "مهندسیکالا",
      "image": "https://dkstatics-public.digikala.com/digikala-products/bf2762b5fef3644adbbdb976c802d032651071cb_1780649694.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-21936908/",
      "match": "none"
    },
    {
      "id": 20938266,
      "title": "کیت آموزشی مدل مدار الکتریکی بسته 4 عددی",
      "brand": "متفرقه",
      "price": 55000,
      "in_stock": true,
      "seller": "نوشت افزار پاکسیم",
      "rating": 4.0,
      "rating_count": 9,
      "image": "https://dkstatics-public.digikala.com/digikala-products/1a3430e8748bb50f55b53e103aa3d76a8e518814_1763738601.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-20938266/",
      "match": "none"
    },
    {
      "id": 3713750,
      "title": "برد الکترونیکی گیرنده بلوتوث کد XY-BT",
      "brand": "متفرقه",
      "price": 285000,
      "in_stock": true,
      "seller": "تجهیز استور",
      "rating": 4.2,
      "rating_count": 2775,
      "image": "https://dkstatics-public.digikala.com/digikala-products/8b5fc92e82a8df0fb52e69c45751a9b11aa23d34_1604918123.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-3713750/",
      "match": "all"
    },
    {
      "id": 8378840,
      "title": "کیت آموزشی جامع الکترونیک مهندسیکا مدل ARDUINO+55 ",
      "brand": "مهندسیکا",
      "price": 37492840,
      "price_before_discount": 39886000,
      "discount_pct": 6,
      "in_stock": true,
      "seller": "مهندسیکالا",
      "rating": 4.6,
      "rating_count": 8,
      "image": "https://dkstatics-public.digikala.com/digikala-products/e3736d0c581e0a99a4416d8c7548e41bc8385fc6_1651039150.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-8378840/",
      "match": "none"
    },
    {
      "id": 878062,
      "title": "کیت سرگرمی الکترونیک پنج پروژه در یک ماژول آردوینو برند مهندسیکا AD00127",
      "brand": "متفرقه",
      "price": 9351470,
      "price_before_discount": 9948370,
      "discount_pct": 6,
      "in_stock": true,
      "seller": "مهندسیکالا",
      "rating": 2.9,
      "rating_count": 9,
      "image": "https://dkstatics-public.digikala.com/digikala-products/4073528.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-878062/",
      "match": "none"
    },
    {
      "id": 5092752,
      "title": "کیت آموزشی مدل آزمایشگاه الکترونیک 1",
      "brand": "متفرقه",
      "price": 1999990,
      "in_stock": true,
      "seller": "وحید کیت",
      "rating": 4.5,
      "rating_count": 8,
      "image": "https://dkstatics-public.digikala.com/digikala-products/dc03280df0fbc275c50b52a59a3cf2a82aa8ea58_1620239448.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-5092752/",
      "match": "none"
    },
    {
      "id": 1588141,
      "title": "دستگاه تستر قطعات الکترونیکی مدل LCR-T4",
      "brand": "متفرقه",
      "price": 2600000,
      "in_stock": true,
      "seller": "دلبای",
      "rating": 3.9,
      "rating_count": 261,
      "image": "https://dkstatics-public.digikala.com/digikala-products/111071586.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-1588141/",
      "match": "all"
    },
    {
      "id": 11572129,
      "title": "کتاب آموزش کاربردی الکترونیک برای نوجوانان و جوانان اثر کیت بریندلی انتشارات نبض دانش",
      "brand": "انتشارات نبض دانش",
      "price": 650000,
      "in_stock": true,
      "seller": "کتاب باز اندیشه",
      "rating": 3.6,
      "rating_count": 13,
      "image": "https://dkstatics-public.digikala.com/digikala-products/1bba2374b12cd48e9e44f57384d0ba8c682bd009_1685990303.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-11572129/",
      "match": "none"
    },
    {
      "id": 7185356,
      "title": "کیت آموزشی مدل آزمایشگاه الکترونیک",
      "brand": "متفرقه",
      "price": 1850000,
      "in_stock": true,
      "seller": "نسیم تحول",
      "rating": 4.0,
      "rating_count": 67,
      "image": "https://dkstatics-public.digikala.com/digikala-products/df5ff6781af5920d6b9a59b02f8f7ccc06835680_1638193701.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-7185356/",
      "match": "none"
    },
    {
      "id": 1006545,
      "title": "کیت آموزشی وحید کیت مدل بازی های الکترونیک کد V.K 102",
      "brand": "متفرقه",
      "price": 449990,
      "in_stock": true,
      "seller": "وحید کیت",
      "rating": 3.3,
      "rating_count": 42,
      "image": "https://dkstatics-public.digikala.com/digikala-products/4761405.jpg?x-oss-process=image/resize,m_lfit,h_600,w_600/quality,q_90",
      "url": "https://www.digikala.com/product/dkp-1006545/",
      "match": "none"
    }
  ],
  "matches": {
    "all": 3,
    "some": 0,
    "none": 19
  }
}
````

### snappshop (`ss_search`)

Query: `الکترونیکی`

Status: `success`
Duration: `2130 ms`
MCP tool requests: `1`
Top-level extracted records: `12`

Arguments sent:

````json
{
  "query": "الکترونیکی",
  "page": 1
}
````

Complete MCP response:

````json
{
  "total": 739,
  "page": 1,
  "pages": 62,
  "items": [
    {
      "id": "EeYGow",
      "product_id": 2067615048,
      "title": "دستگاه سیگار الکترونیکی آیرود مدل ایکس ۳",
      "price": 3666000,
      "list_price": 4700000,
      "discount_percent": 22,
      "colors": [
        "مشکی",
        "نقره‌ای-طوسی",
        "سبز",
        "بنفش",
        "قهوه‌ای"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-2067615048"
    },
    {
      "id": "lLjk9P",
      "product_id": 1432641723,
      "title": "دستگاه سیگار الکترونیکی آیکاس مدل Bonds",
      "price": 5952000,
      "list_price": 6400000,
      "discount_percent": 8,
      "colors": [
        "مشکی",
        "نقره‌ای-طوسی",
        "آبی",
        "قرمز"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1432641723"
    },
    {
      "id": "wjKdL4",
      "product_id": 1114660452,
      "title": "دستگاه سیگار الکترونیکی آیکاس مدل ایلوما وان IQOS ILUMA ONE",
      "price": 12465000,
      "list_price": 13850000,
      "discount_percent": 10,
      "colors": [
        "مشکی",
        "زرد",
        "سبز",
        "آبی",
        "قرمز",
        "بنفش"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1114660452"
    },
    {
      "id": "5eVYN5",
      "product_id": 1173125163,
      "title": "دستگاه سیگار الکترونیکی آیکاس ایلوما مدل آی وان IQOS ILUMA i ONE",
      "price": 13020000,
      "list_price": 15000000,
      "discount_percent": 14,
      "colors": [
        "مشکی",
        "سبز",
        "آبی",
        "بنفش",
        "نارنجی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1173125163"
    },
    {
      "id": "PdvjMG",
      "product_id": 674470763,
      "title": "دستگاه سیگار الکترونیکی ان میت مدل MK 1",
      "price": 3950000,
      "list_price": 4200000,
      "discount_percent": 6,
      "colors": [
        "مشکی",
        "نقره‌ای-طوسی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-674470763"
    },
    {
      "id": "NzEXdE",
      "product_id": 852068563,
      "title": "دستگاه سیگار الکترونیکی آیکاس ایلوما مدل آی وان IQOS ILUMA i ONE",
      "price": 13065000,
      "list_price": 14100000,
      "discount_percent": 8,
      "colors": [
        "نقره‌ای-طوسی",
        "سبز",
        "آبی",
        "بنفش",
        "نارنجی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-852068563"
    },
    {
      "id": "KzlyZM",
      "product_id": 2083780967,
      "title": "دستگاه سیگار الکترونیکی آیکاس ایلوما مدل پرایم آی IQOS ILUMA Prime i",
      "price": 33480000,
      "list_price": 35000000,
      "discount_percent": 5,
      "colors": [
        "آبی",
        "بنفش"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-2083780967"
    },
    {
      "id": "LPPykA",
      "product_id": 728013770,
      "title": "دستگاه سیگار الکترونیکی مدل یو سونیک یو وان به همراه یک باکس سیگار",
      "price": 2500000,
      "list_price": 3500000,
      "discount_percent": 29,
      "colors": [
        "نقره‌ای-طوسی",
        "سفید"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-728013770"
    },
    {
      "id": "1dX5Em",
      "product_id": 1725806367,
      "title": "دستگاه سیگار الکترونیکی آیکاس مدل iluma Galaxy Blue Limited",
      "price": 29795000,
      "list_price": 34520000,
      "discount_percent": 14,
      "colors": [
        "آبی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-1725806367"
    },
    {
      "id": "8WPwxw",
      "product_id": 212083421,
      "title": "دستگاه سیگار الکترونیکی آیکاس ایلوما مدل آی استاندارد IQOS Iluma i Standard",
      "price": 26480000,
      "list_price": 27800000,
      "discount_percent": 5,
      "colors": [
        "مشکی",
        "آبی"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-212083421"
    },
    {
      "id": "Ma12Ly",
      "product_id": 596589853,
      "title": "دستگاه سیگار الکترونیکی آیکاس مدل Remix Limited Edition",
      "price": 57998000,
      "list_price": 61700000,
      "discount_percent": 6,
      "colors": [
        "بنفش"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-596589853"
    },
    {
      "id": "Z824LA",
      "product_id": 133606885,
      "title": "دستگاه سیگار الکترونیکی آیکاس مدل ONE i طرح New purple",
      "price": 19800000,
      "list_price": 21000000,
      "discount_percent": 6,
      "colors": [
        "بنفش"
      ],
      "badge": "خرید قسطی",
      "url": "https://snappshop.ir/product/snp-133606885"
    }
  ],
  "brands": [
    {
      "id": "gypN9D",
      "name": "گارنت",
      "name_en": "Garnet"
    },
    {
      "id": "gR28Wg",
      "name": "ایکیا",
      "name_en": "Ikea"
    },
    {
      "id": "DBjMZD",
      "name": "واستر",
      "name_en": "Vaster"
    },
    {
      "id": "g3eMQq",
      "name": "سونی",
      "name_en": "Sony"
    },
    {
      "id": "D5Vrng",
      "name": "انتشارات سروش",
      "name_en": "Soroush Publications"
    },
    {
      "id": "Db1vRq",
      "name": "نشر علم",
      "name_en": "Elm Publication"
    },
    {
      "id": "qOPo2D",
      "name": "انتشارات سبزان",
      "name_en": "Sabzan Pub"
    },
    {
      "id": "0MEQw0",
      "name": "بکلیت",
      "name_en": "Backlit"
    },
    {
      "id": "qPQWwD",
      "name": "فیدکس تولز",
      "name_en": "Fidex Tools"
    },
    {
      "id": "g3YJBq",
      "name": "ترا",
      "name_en": "Terea"
    },
    {
      "id": "D5R5Ag",
      "name": "نوسو",
      "name_en": "NUSO"
    },
    {
      "id": "0XmVzq",
      "name": "شوبرت",
      "name_en": "Schobert"
    },
    {
      "id": "gmOpdq",
      "name": "صدرا سیف",
      "name_en": "Sadra Safe"
    },
    {
      "id": "DBeN7q",
      "name": "آیکاس",
      "name_en": "IQOS"
    },
    {
      "id": "5DbVYD",
      "name": "نمودار کنترل",
      "name_en": "Nemoodar Control"
    },
    {
      "id": "0kL3Eq",
      "name": "لمه",
      "name_en": "LEME"
    },
    {
      "id": "0WKlZ0",
      "name": "جوی",
      "name_en": "Joy"
    },
    {
      "id": "DB7j7g",
      "name": "سدید",
      "name_en": "Sadid"
    },
    {
      "id": "DBevyq",
      "name": "هیتس",
      "name_en": "Heets"
    },
    {
      "id": "Do1M70",
      "name": "موفی",
      "name_en": "Mofee"
    },
    {
      "id": "gGaRrq",
      "name": "فوندز",
      "name_en": "Fondz"
    },
    {
      "id": "DjYKbq",
      "name": "آرتمیس",
      "name_en": "Artemis"
    },
    {
      "id": "nqPeQD",
      "name": "ارس",
      "name_en": "Aras"
    },
    {
      "id": "0KdJGq",
      "name": "انتشارات سمت",
      "name_en": "Samt Pub"
    },
    {
      "id": "09l4pg",
      "name": "انتشارات ادیبان روز",
      "name_en": "Adibane Rooz Pub"
    }
  ]
}
````
