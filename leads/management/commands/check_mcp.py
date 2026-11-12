import argparse
import asyncio
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from leads.adapters import _arguments
from leads.mcp_client import SOURCE_REGISTRY, source_session
from leads.sources import CITY_CENTERS, _records


class Command(BaseCommand):
    help = "Connect to one or both real MCP servers and perform a small live place search."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=[*SOURCE_REGISTRY, "all"], default="all")
        parser.add_argument("--query", default="طلافروشی")
        parser.add_argument("--city", default="تهران")
        parser.add_argument("--schema-only", action="store_true", help="List live allowlisted tool schemas without calling source websites.")

    def handle(self, *args, **options):
        sources = settings.ENABLED_MCP_SOURCES if options["source"] == "all" else [options["source"]]
        if not sources:
            raise CommandError("No MCP source is enabled in ENABLED_MCP_SOURCES.")
        point = None if options["schema_only"] else next((coords for city, coords in CITY_CENTERS.items() if city == options["city"]), None)
        if not options["schema_only"] and not point:
            raise CommandError("City not in the built-in map-center list. Try تهران، اصفهان، مشهد، شیراز or another supported major city.")
        for source in sources:
            try:
                result = asyncio.run(self._inspect(source) if options["schema_only"] else self._probe(source, options["query"], options["city"], point))
            except Exception as exc:
                raise CommandError(f"{source}: live check failed ({type(exc).__name__}: {exc})") from exc
            if options["schema_only"]:
                self.stdout.write(json.dumps({"source": source, "tools": result}, ensure_ascii=True, indent=2))
                continue
            self.stdout.write(self.style.SUCCESS(
                f"{source}: connected; tools={','.join(result[0])}; results={result[1]}; details={'ok' if result[2] else 'not available'}"
            ))

    async def _inspect(self, source):
        config = SOURCE_REGISTRY[source]
        async with source_session(source) as client:
            return {
                name: getattr(client.tools[name], "input_schema", None) or getattr(client.tools[name], "inputSchema", {})
                for name in config["tools"].values()
            }

    async def _probe(self, source, query, city, point):
        config = SOURCE_REGISTRY[source]
        async with source_session(source) as client:
            if source == "rasmio":
                tool = config["tools"]["search"]
                args = _arguments(client, tool, {"query": query, "city": city, "page": 1, "limit": 3})
                result = await client.call(tool, args)
                return [tool], len(_records(result.data)), False
            if source == "emalls":
                tool = config["tools"]["search"]
                args = _arguments(client, tool, {"query": query, "page": 1, "limit": 3})
                result = await client.call(tool, args)
                products = _records(result.data)
                detail_ok = False
                if products:
                    product_id = products[0].get("id") or products[0].get("product_id")
                    if product_id:
                        offers_tool = config["tools"]["offers"]
                        offers_args = _arguments(client, offers_tool, {"product_id": str(product_id), "city": city})
                        offers = await client.call(offers_tool, offers_args)
                        rows = _records(offers.data)
                        shop_id = next((row.get("shop_id") or row.get("id") for row in rows if row.get("shop_id") or row.get("id")), None)
                        if shop_id:
                            profile_tool = config["tools"]["detail"]
                            profile = await client.call(profile_tool, _arguments(client, profile_tool, {"shop_id": str(shop_id)}))
                            detail_ok = isinstance(profile.data, dict)
                names = [name for name in config["tools"].values() if name in client.tools]
                return names, len(products), detail_ok
            if source == "basalam":
                tool = config["tools"]["search"]
                result = await client.call(tool, _arguments(client, tool, {"query": query, "page": 1, "limit": 3}))
                rows = _records(result.data)
                profile_ok = False
                shop_id = next((row.get("shop_id") or row.get("vendor_id") for row in rows if row.get("shop_id") or row.get("vendor_id")), None)
                if shop_id:
                    profile_tool = config["tools"]["detail"]
                    profile = await client.call(profile_tool, _arguments(client, profile_tool, {"shop_id": str(shop_id)}))
                    profile_ok = isinstance(profile.data, dict)
                return [tool, config["tools"]["detail"]], len(rows), profile_ok
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
