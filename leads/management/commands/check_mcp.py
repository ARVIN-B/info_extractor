import argparse
import asyncio
import json

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from leads.adapters import SOURCE_ADAPTERS, _arguments
from leads.mcp_client import SOURCE_REGISTRY, source_session
from leads.sources import CITY_CENTERS, _records


class Command(BaseCommand):
    help = "Connect to configured MCP servers and perform a small, source-specific live search."

    def add_arguments(self, parser):
        parser.add_argument("--source", choices=[*SOURCE_REGISTRY, "all"], default="all")
        parser.add_argument("--query", default="طلافروشی")
        parser.add_argument("--city", default="تهران")
        parser.add_argument("--schema-only", action="store_true", help="List live allowlisted tool schemas without calling source websites.")

    def handle(self, *args, **options):
        sources = settings.ENABLED_MCP_SOURCES if options["source"] == "all" else [options["source"]]
        if not sources:
            raise CommandError("No MCP source is enabled in ENABLED_MCP_SOURCES.")
        point = None
        geographic_sources = {"neshan", "balad"}.intersection(sources)
        if not options["schema_only"] and geographic_sources:
            point = next((coords for city, coords in CITY_CENTERS.items() if city == options["city"]), None)
        if geographic_sources and not options["schema_only"] and not point:
            raise CommandError("City not in the built-in map-center list. Try تهران، اصفهان، مشهد، شیراز or another supported major city.")
        failures = []
        for source in sources:
            try:
                result = asyncio.run(self._inspect(source) if options["schema_only"] else self._probe(source, options["query"], options["city"], point))
            except Exception as exc:
                message = f"{source}: live check failed ({type(exc).__name__}: {exc})"
                failures.append((source, message))
                self.stderr.write(self.style.ERROR(message))
                continue
            if options["schema_only"]:
                self.stdout.write(json.dumps({"source": source, "tools": result}, ensure_ascii=True, indent=2))
                continue
            self.stdout.write(self.style.SUCCESS(
                f"{source}: connected; tools={','.join(result[0])}; results={result[1]}; details={result[2]}"
            ))
        if failures:
            raise CommandError(f"MCP check failed for: {', '.join(source for source, _ in failures)}")

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
            if source in SOURCE_ADAPTERS:
                adapter = SOURCE_ADAPTERS[source]
                called_tools = set()

                async def invoke(adapter_client, tool_name, arguments):
                    called_tools.add(tool_name)
                    return await adapter_client.call(tool_name, arguments)

                result = await adapter.discover(client, invoke, query, city, "", 1)
                detail_tool = config["tools"].get("detail")
                detail_state = "not available" if not detail_tool else (
                    "ok" if detail_tool in called_tools else "not exercised"
                )
                names = [name for name in config["tools"].values() if name in client.tools]
                return names, len(result.records), detail_state
            search_tool = config["tools"].get("nearby", config["tools"]["search"])
            if source == "neshan":
                result = await client.call(search_tool, {"query": query, "near": city, "limit": 3})
            else:
                result = await client.call(search_tool, {"what": query, "lat": point[0], "lng": point[1], "radius_km": 20, "limit": 3})
            names = [tool for tool in client.tools if tool in config["tools"].values()]
            rows = _records(result.data)
            first = next((row for row in rows if row.get("id")), None)
            detail_ok = False
            detail_tool = config["tools"].get("detail")
            if first and detail_tool:
                detail_arg = "place_id" if source == "neshan" else "id"
                detail = await client.call(detail_tool, {detail_arg: str(first["id"])})
                detail_ok = isinstance(detail.data, dict)
            detail_state = "not available" if not detail_tool else "ok" if detail_ok else "not exercised"
            return names, len(rows), detail_state
