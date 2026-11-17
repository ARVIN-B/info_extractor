# Debugging and Fixing MCP Integration — info_extractor

Repository: https://github.com/ARVIN-B/info_extractor

I want you to investigate and fix the current MCP integration issues. Before making any changes, understand the history of the problem, the previous fix, and the remaining issues described below.

## 1. Previous Problem: Unexpected KeyError

In the previous deployment, two MCP sources failed:

```text
iran_jobs: Unexpected KeyError; see server logs.
torob: Unexpected KeyError; see server logs.
```

After investigating the code, we identified the following problem in `leads/sources.py`, inside `_search_source()`:

```python
config = SOURCE_REGISTRY[source]
geocode_tool = config["tools"]["search"]
search_tool = config["tools"].get("nearby", geocode_tool)
detail_tool = config["tools"]["detail"]
```

The problem was that the MCP registry did not define a `detail` tool for these two sources.

The registry configuration was:

```python
"torob": {
    "tools": {
        "search": "tb_find_shops"
    }
}
```

```python
"iran_jobs": {
    "tools": {
        "search": "job_companies"
    }
}
```

Therefore, accessing:

```python
config["tools"]["detail"]
```

caused:

```text
KeyError: 'detail'
```

## 2. Previous Fix

We identified that not every MCP source supports a detail tool.

The initial correction was to make the detail tool optional:

```python
detail_tool = config["tools"].get("detail")
```

The important architectural decision is:

- A source must not require a detail tool if its MCP server does not provide one.
- Sources that only support searching must still work.
- Detail enrichment must be optional.
- Missing optional tools must never crash the entire extraction process.
- Existing sources that support detail lookup must continue working as before.

However, this was only part of the problem. We also discovered that the `check_mcp` management command still contained assumptions about the old source structure.

## 3. Current Problem: MCP Health Check and Argument Mismatch

The current errors are related to the following sources:

- Torob (`torob-mcp`)
- Iran Jobs (`iran-jobs-mcp`)

### A. Torob problem

Running:

```bash
python manage.py check_mcp --source torob --query "فروشگاه موبایل" --city "تهران"
```

produced:

```text
CommandError: torob: live check failed
(MCPSourceError: Invalid arguments for tb_find_shops:
'query' is a required property)
```

We inspected `leads/adapters.py` and found that `TorobShopAdapter` already sends the appropriate argument:

```python
args = _arguments(client, tool, {
    "query": query,
    "city": city or province or None,
    "kind": "all",
    "page": 0,
    "limit": min(30, limit)
})
```

This indicates that the main extraction adapter and the health-check implementation are not following the same argument contract.

The problem is in `leads/management/commands/check_mcp.py`.

Its `_probe()` method does not have dedicated branches for Torob and Iran Jobs. Instead, both fall through to a generic branch designed for geographic sources such as Neshan and Balad.

That generic branch sends arguments similar to:

```python
{
    "what": query,
    "lat": point[0],
    "lng": point[1],
    "radius_km": 20,
    "limit": 3
}
```

But Torob expects a `query` argument, not `what`, `lat`, or `lng`.

Additionally, the generic branch attempts to access:

```python
config["tools"]["detail"]
```

which recreates the original KeyError for sources that do not provide a detail tool.

### B. Iran Jobs problem

Running:

```bash
python manage.py check_mcp --source iran_jobs --query "شرکت نرم افزاری" --city "تهران"
```

produced:

```text
iran_jobs: connected; tools=job_companies; results=0; details=not available
```

The MCP server connects successfully, but no results are returned.

We inspected the current `IranJobsCompanyAdapter`:

```python
args = _arguments(client, tool, {
    "query": query,
    "page": 1,
    "site": "all"
})
```

However, the fake schema defined in `leads/tests.py` for `job_companies` currently looks like this:

```python
"job_companies": SimpleNamespace(input_schema={
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "site": {"type": "string"},
        "page": {"type": "integer"}
    }
})
```

Notice that this schema contains `name`, not `query`.

This raises an important possibility: `_arguments()` may be removing the unsupported `query` argument, resulting in an empty search request and zero results.

However, the fake test schema does not prove that the deployed MCP server has the same schema.

**Do not assume that `query` or `name` is the correct argument until the actual MCP tool schema has been inspected.**

## 4. What We Need To Do

Please investigate and fix the issues systematically.

### Step 1 — Inspect the existing implementation

Review these files and their related code:

- `leads/mcp_client.py`
- `leads/sources.py`
- `leads/adapters.py`
- `leads/management/commands/check_mcp.py`
- `leads/tests.py`

Understand how the MCP registry, adapters, argument validation, source discovery, detail enrichment, and health checks work together.

Do not assume that the health-check implementation and the actual extraction implementation currently behave identically.

### Step 2 — Fix the health-check architecture

Update `check_mcp.py` so each source uses the correct tool and argument contract.

Requirements:

1. Torob must use its actual search tool: `tb_find_shops`.
2. Iran Jobs must use its actual search tool: `job_companies`.
3. Neshan and Balad must continue using their geographic search arguments.
4. Sources must not be forced through an unrelated generic search implementation.
5. Missing detail tools must be handled safely.
6. A source without a detail tool should report that detail lookup is unavailable, rather than failing.
7. The health check must accurately report connection status, tool names, result count, and detail availability.
8. Avoid duplicating argument-building logic unnecessarily between adapters and health checks.

Where practical, reuse the existing adapter logic or introduce a shared helper so the health check and production extraction cannot silently diverge.

### Step 3 — Verify the real MCP schemas

The actual MCP input schemas must be treated as the source of truth.

The management command already supports:

```bash
python manage.py check_mcp --source torob --schema-only
python manage.py check_mcp --source iran_jobs --schema-only
```

Inspect and improve this functionality if necessary.

I will provide the actual output of these commands if it is not available in your environment.

Do not invent or assume the required arguments for either MCP server.

In particular:

- Determine whether `tb_find_shops` requires `query` and which optional arguments it supports.
- Determine whether `job_companies` expects `name`, `query`, or another field.
- Ensure the corresponding adapters send arguments that match the real schema.
- Update the fake schemas in `leads/tests.py` to reflect the verified contracts.

If the live schemas cannot be accessed from your environment, clearly identify what information is missing and ask me for the schema output before making assumptions about the correct argument names.

### Step 4 — Fix and improve tests

Add or update tests covering:

- Torob search without a detail tool.
- Iran Jobs search without a detail tool.
- Correct argument mapping for each source.
- A missing optional detail tool.
- A source with a valid detail tool.
- Schema-based argument filtering.
- A failed MCP source not stopping other sources.
- Health checks reporting errors accurately.

Make sure the tests cover the original KeyError scenario as well as the current argument mismatch.

### Step 5 — Preserve the existing architecture

This project uses independent MCP sources.

The following behavior must remain intact:

- One source failing must not stop other sources.
- Successful results from other sources must be preserved.
- Existing normalization and deduplication must continue working.
- Evidence collection must remain intact.
- Existing source adapters must not be unnecessarily rewritten.
- Do not break existing Neshan, Balad, Emalls, or Basalam integrations.
- Do not introduce unnecessary dependencies or unrelated architectural changes.

## 5. Deployment and Version Consistency

The deployed environment previously showed these package versions:

```text
torob-mcp==0.2.2
iran-jobs-mcp==0.2.1
digikala-mcp==0.6.2
snappshop-mcp==0.2.1
```

But the registry configuration contained older pinned versions:

```text
torob-mcp==0.2.1
iran-jobs-mcp==0.2.0
digikala-mcp==0.6.1
snappshop-mcp==0.2.0
```

Investigate whether this version mismatch is intentional or accidental.

Do not automatically upgrade or downgrade packages without checking compatibility and the actual project requirements.

Ensure the registry, requirements files, and deployed package versions are consistent.

## 6. Expected Deliverables

After your investigation and implementation:

1. Explain the exact root cause of the original KeyError.
2. Explain how the previous fix addressed it and whether any remaining code still had the same unsafe assumption.
3. Explain the root cause of the Torob health-check failure.
4. Explain whether Iran Jobs has an argument-name mismatch, based on the actual schema.
5. List every file you modified and why.
6. Provide the tests you added or changed and their results.
7. Provide the exact commands I should run on the server to verify both sources.
8. Identify any remaining issue that requires access to the deployed MCP server.

**Important:** Do not simply suppress exceptions or make the health check report success when a source is not working. The goal is to fix the actual integration and keep the health-check results truthful.

First investigate the current code, then make the smallest reliable changes that solve the problems without breaking existing integrations.