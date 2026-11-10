import argparse
import asyncio

from django.core.management.base import BaseCommand, CommandError

from leads.mcp_client import SOURCE_REGISTRY, source_session
from leads.sources import CITY_CENTERS, _records


class Command(BaseCommand):
    help = "Connect to one or both real MCP servers and perform a small live place search."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=[*SOURCE_REGISTRY, "all"], default="all")
        parser.add_argument("--query", default="طلافروشی")
        parser.add_argument("--city", default="تهران")

    def handle(self, *args, **options):
        sources = list(SOURCE_REGISTRY) if options["source"] == "all" else [options["source"]]
        point = next((coords for city, coords in CITY_CENTERS.items() if city == options["city"]), None)
        if not point:
            raise CommandError("City not in the built-in map-center list. Try تهران، اصفهان، مشهد، شیراز or another supported major city.")
        for source in sources:
            try:
                result = asyncio.run(self._probe(source, options["query"], options["city"], point))
            except Exception as exc:
                raise CommandError(f"{source}: live check failed ({type(exc).__name__}: {exc})") from exc
            self.stdout.write(self.style.SUCCESS(
                f"{source}: connected; tools={','.join(result[0])}; results={result[1]}; details={'ok' if result[2] else 'not available'}"
            ))

    async def _probe(self, source, query, city, point):
        config = SOURCE_REGISTRY[source]
        async with source_session(source) as client:
            search_tool = config["tools"].get("nearby", config["tools"]["search"])
            if source == "neshan":
                result = await client.call(search_tool, {"query": query, "near": city, "limit": 3})
            else:
                result = await client.call(search_tool, {"what": query, "lat": point[0], "lng": point[1], "radius_km": 20, "limit": 3})
            names = [tool for tool in client.tools if tool in config["tools"].values()]
            rows = _records(result.data)
            first = next((row for row in rows if row.get("id")), None)
            detail_ok = False
            if first:
                detail_arg = "place_id" if source == "neshan" else "id"
                detail = await client.call(config["tools"]["detail"], {detail_arg: str(first["id"])})
                detail_ok = isinstance(detail.data, dict)
            return names, len(rows), detail_ok
