from django.core.management.base import BaseCommand, CommandError

from leads.web_search import WebServiceError, fetch_searxng_page


class Command(BaseCommand):
    help = "Run a small live connection check against the configured SearXNG instance."

    def add_arguments(self, parser):
        parser.add_argument("--query", default="کسب‌وکار ایران شماره تماس")
        parser.add_argument("--page", type=int, default=1)

    def handle(self, *args, **options):
        page = options["page"]
        if page < 1:
            raise CommandError("--page must be at least 1.")
        counter = [0]
        try:
            results = fetch_searxng_page(options["query"], page, request_counter=counter)
        except WebServiceError as exc:
            raise CommandError(str(exc)) from None
        engines = sorted({engine for item in results for engine in item.get("engines", []) if isinstance(engine, str)})
        self.stdout.write(self.style.SUCCESS(
            f"SearXNG connected: page={page}; results={len(results)}; engines={len(engines)}; requests={counter[0]}"
        ))
