# Implementation plan: large, resumable discovery and query intelligence

## Audit and technical assessment

- [x] Read `docs/new_update3.md` and `docs/new_update4.md` in full; record the category-name search requirement from the request.
- [x] Inspect Django form/model, Celery lifecycle, adapters, MCP schemas/contracts, source persistence, exports, tests, settings, and deployment documentation.
- [x] Preserve existing working architecture: Django/SQLite-compatible ORM, Celery, independent MCP adapters, evidence records, conservative matching, and source-specific rate limiting.
- [x] Confirm `SearchJob.max_results` is a `PositiveSmallIntegerField` (supports 5,000), while form, template, call budgets, one-task source lifecycle, adapter page caps, and dedup implementation constrain larger jobs.
- [x] Confirm Torob supports pages 0–50, Iran Jobs pages 1–500, marketplace schemas expose page/page_size limits; initial adapters capped pagination at five pages or read page 1. Geographic map sources initially had no cursor.
- [x] Confirm initial Celery execution processed each job in one invocation; stale recovery restarted incomplete source work and query/page/area progress was not durable.
- [x] Verify provider API claims against official Neshan Maps MCP, Basalam API documentation, and Torob Shop API documentation; do not infer general discovery access or numerical quotas from these.

### Independent decisions

1. Use equal-fair initial shares with round-robin bounded source batches and redistribution based on actual new unique leads. Do not weight by historical performance yet: there is no reliable per-source history table, and an unvalidated yield model can starve low-volume sources.
2. Manage unique-result targets separately from MCP request budgets. Keep global and per-source limits configurable, reserve a minimum opportunity for every eligible selected source, and stop honestly at a hard total cap.
3. Keep current discovery/detail adapter chains for now. Marketplace profiles can be the only legitimate source of vendor identity/contact data; a full two-stage enrichment redesign needs provider-specific contracts and may reduce currently available lead quality. Limit detail calls through explicit adapter call costs and retain partial discovery on failure.
4. Initial pagination was insufficient across those adapters. Pagination now follows schema page bounds and persists per-page/per-query state; map sources save area/variant cursors. Coverage remains limited by upstream data and undocumented limits.
5. Remaining bottlenecks are provider quota/rate limits, marketplace detail calls, SQLite write serialization, unknown total result counts, pages without stable cursors, and replay if a worker dies mid-page. Celery now schedules bounded batches.
6. Initial defaults of 40 calls/source and 200/job were restrictive; defaults are now 500/source and 4,000/job with a 500-call hard per-source batch ceiling. Page/variant/area boundaries normally pause earlier. All caps are finite and configurable; provider throttles remain untouched.
7. `_find_match` originally scanned every lead and JSON source ID for each record. Indexed lookups by source ID, national ID, and normalized name now avoid the full-table scan while preserving conservative predicates and evidence writes. A per-job in-memory index remains a possible further optimization.
8. Initial one-task execution was insufficient. Jobs now persist page/query/area checkpoints and queue bounded continuation batches; stale recovery retains checkpoints. A worker lost mid-page may repeat that page.
9. For known daily/monthly quotas, persist cooldown until the provider's explicit reset or configured conservative interval, continue other sources, and schedule continuation. Do not guess a reset or evade limits.
10. For concurrent large jobs, keep per-user active-job limits, distributed source locks/cooldowns, bounded per-invocation request work, global/per-source caps, and explicit SQLite concurrency constraints; recommend PostgreSQL for sustained production concurrency.

## Implementation checklist

- [x] Add configurable 5,000 result maximum, finite request budgets, query-expansion settings, and accurate form/template validation.
- [x] Add deterministic Persian category taxonomy and category-intent detection. Category matches search aliases and source-reported category labels where previously observed.
- [x] Add validated query expansion: original query first, deterministic synonyms/categories, optional OpenAI-compatible provider via existing `httpx`, timeout/token/variant limits, DB cache, and nonfatal fallback.
- [x] Preserve schema-aware parameter construction in every Adapter; pagination parameters are emitted only when supported by the connected schema.
- [x] Expand Emalls, Basalam, and Rasmio pages beyond the former five-page cap and add pagination for Torob and Iran Jobs; page count honors schema maximum and local ceiling. Existing marketplace product profile calls are preserved.
- [x] Persist page, query-variant, and geographic area/variant checkpoints and queue continuation tasks. Saved rows and checkpoints survive stale recovery. A crash during a page can replay it; this is at-least-once with dedup, not exactly-once.
- [x] Recalculate equal source result shares against the remaining unique-lead target and retain separate per-source/global MCP call ceilings.
- [x] Narrow dedup DB queries to source-record JSON ID, national ID, and indexed normalized-name candidates without changing the conservative identity predicates or evidence writes.
- [x] Expose recognized category intent and accepted variants in the Persian job view; document current budget/source statuses and coverage constraints.
- [x] Add deterministic tests for category queries, Persian normalization, configured 5,000 limit, and validated/cached LLM expansion; existing adapter, rate-limit, cancellation, recovery, dedup, and export tests remain active.
- [x] Add page-level continuation and bounded per-source work; each continuation gives every unfinished source one bounded page/query turn. Test checkpoint return/resume and queued job continuation.
- [x] Fingerprint catalog page identities and stop a query variant when an upstream repeats an earlier page; test same-page resume versus repeated-page detection.
- [x] Add a large-job dedup regression test that asserts two bounded lead lookups and the indexed normalized-name filter.
- [x] Run the full project test suite, Django checks, migration check, and package consistency checks. Real external searches were not executed in this turn to avoid spending provider quota without an explicit search target.
- [x] Update README and `.env.example` with configuration, provider review, realistic limits, migration/deployment commands, and provider-dependent limitations.

## Implementation evidence and limitations

- Search max is 5,000 by default (model field already supports it); internal call defaults are 500/source and 4,000/job. Operators can lower or raise these finite caps per provider policy.
- Adapter page ceilings now follow the live schema. Sources that provide no page-size contract still have a conservative local cap; this is not a claim of exhaustive provider coverage.
- Query expansion is opt-in for LLM and has a deterministic-only default. LLM calls use the existing `httpx` dependency, configurable endpoint/model/key, timeout, max tokens, response validation, cache, and fallback.
- Page, query, record-offset, and geographic checkpoints continue through Celery batches. If a worker dies inside a page, it may replay that page; dedup prevents duplicate lead rows, but provider detail calls can repeat. `SEARCH_PAGES_PER_BATCH=1` and finite request caps bound normal work. Five thousand remains a target, not a guarantee.
- The dedup regression test seeds 301 leads and asserts matching uses two lead queries, with the second narrowed by normalized name. This verifies query shape, not end-to-end latency under production load. Providers without stable cursors/totals may still truncate or repeat records; monitor task duration and provider budgets in production.
- Provider quota figures remain account-specific or unpublished; see the links and caveats in README.
- Deployment: `python manage.py migrate`, then restart web, Celery workers and Celery Beat. Windows local equivalent: `\.venv\Scripts\python.exe manage.py migrate`.
