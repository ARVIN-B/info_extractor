# اجرای Celery در چابکان

پروژه از `config.settings` استفاده می‌کند. ورودی `app` فقط برای سازگاری با دستور `celery -A app` در راهنمای چابکان است و همان Celery app اصلی پروژه را بارگذاری می‌کند.

## تنظیم Redis

در متغیرهای محیطی سرویس، آدرس Redis چابکان را به یکی از نام‌های `CELERY_BROKER_URL`، `REDIS_URL` یا `BROKER_URL` اضافه کنید. اولویت با `CELERY_BROKER_URL` است. آدرس باید از داخل محیط اپ به Redis قابل دسترس باشد. در production از `filesystem://` استفاده نکنید.

`supervisor.conf` runs the worker and beat under `/app` using the system interpreter `/usr/local/bin/python`; no project virtualenv is used on the server. If that path differs on the host, update both commands. After deploy/restart, check the `celery` and `celery-beat` logs for Redis connectivity, worker readiness, and the recovery schedule.

صف جست‌وجو را worker پردازش می‌کند؛ روشن بودن وب‌سرویس به‌تنهایی کافی نیست. برای پردازش صف فقط worker لازم است، اما beat برای زمان‌بندی بازیابی خودکار jobهایی که worker رها کرده لازم است. اجرای هم‌زمان Redis، worker و وب‌سرویس باید در همان محیط deploy انجام شود.

در اجرای محلی ویندوز و لینوکس، به‌جای Supervisor از فرمان‌های `.venv` ثبت‌شده در README استفاده کنید. نتیجهٔ جست‌وجو در SQLite ذخیره می‌شود؛ مسیر DB باید روی دیسک پایدار deploy باشد.
