# New Update 5 implementation plan

## Audit findings (2026-11-19)

- [x] Read `docs/new_update5.md` in full and inspect the project instructions.
- [x] Confirm the stack is Django templates, SQLite-compatible ORM, Celery, and source-specific MCP adapters; no new package is needed for the priority-one work.
- [x] Confirm mobile-only success is partially implemented: `BusinessLead.has_mobile_phone` is indexed, job totals and public results require it, and migration 0011 backfills it. Businesses without mobile remain stored.
- [x] Confirm the phone pipeline still reads only `phone`, `phones`, and `telephone` via `_field_values`; normalization stores `09…`, not the requested canonical `+989…`.
- [x] Confirm `_safe_source_response` drops unknown fields and truncates nested values, `AdapterResult` projections can discard provider fields before persistence, and `LeadEvidence` has no field path.
- [x] Confirm one business supports multiple phone strings in JSON, but per-number source evidence, use permission, opt-out/suppression, phone-level validation, and reliable phone-level exports are absent.
- [x] Confirm basic business discovery/detail collection and MCP cooldowns exist; there is no independent retryable website/Search enrichment workflow. Existing source inventory and observed limits are recorded in `docs/SOURCE_CATALOG.md` and `docs/SOURCE_CATALOG_AUDIT.md`.
- [x] Confirm current results expose mobile-qualified businesses, but summary analytics are limited to raw source counts and business counts; there are no source-level phone yield or per-phone metrics.

## Scope decisions

1. Implement and validate priority-one recursive phone extraction, canonical Iranian mobile normalization, bounded raw-response retention, per-number provenance, and mobile-only success.
2. Keep original source payloads alongside adapter-normalized fields so the shared extractor can inspect provider-specific nested keys. Enforce byte, depth, item, and string limits; retain an explicit truncation marker. Do not retain unrelated response data without a configurable bound.
3. Use a phone-level model plus append-only evidence rows to preserve multiple numbers and independent sources. Keep existing lead fields as compatibility projections during this migration.
4. Add explicit `unknown` permission state and suppression/opt-out storage. Structural validity or public source appearance must never imply marketing consent. No campaign export may include numbers lacking explicit permission.
5. Implement only bounded, opt-in website contact discovery with URL/IP/redirect/robots/response limits and cache. Do not scrape search-result pages, bypass authentication/CAPTCHA/rate limits, or add a source without a permitted API and reviewed terms/credentials.
6. Make the app report which providers actually returned a mobile; schema connectivity alone is not proof of phone coverage. No external live requests are run without an explicit target because MCP providers have quotas.

## Checklist and implementation status

- [x] Add recursive extraction across dictionaries, sequences, objects, and JSON strings, with bounded depth/nodes/text, cycle protection, field paths, digit normalization, and identifier exclusions.
- [x] Normalize accepted Iranian mobiles to E.164 `+989XXXXXXXXX`; reject landlines, incomplete formats, and long embedded identifiers.
- [x] Preserve adapter raw records and unknown fields with configurable nesting, text, byte, and retention limits; truncated payloads carry an explicit marker.
- [x] Persist a phone per business and append source/record/field-path/raw-number evidence without replacing evidence from another source.
- [x] Keep marketing permission separate from public contact status. Require recorded permission evidence before a phone can be marked marketing-approved; store opt-out and global suppression states.
- [ ] Website contact crawling remains disabled. There is no explicit customer allowlist, approved crawl policy, or safe fetch service configured. Enabling arbitrary user-supplied URL fetches without DNS/IP/redirect/robots controls creates an SSRF risk. This needs a separate audited implementation and production configuration.
- [ ] Search enrichment is not configured: no official Search API provider or credentials are present. Search-result scraping and access-control/rate-limit circumvention are intentionally not introduced.
- [x] Preserve the source adapters' raw records; existing source cooldowns, checkpoints, and per-source failure isolation remain in place.
- [x] Show per-source businesses with mobiles, distinct mobiles, and evidence counts. JSON/Excel exports include per-number provenance; export filters support source, city, category, minimum confidence, and an explicit marketing-permission-only mode.
- [x] Add tests for phone formats, recursive payloads, false-positive identifier keys, multiple sources, shared numbers, suppression, payload limits/retention, export permission gates, and source behavior.
- [x] Update source catalog, README, and deployment/migration notes.
- [x] Run complete app tests, Django checks, migration drift check, package check, compile check, and an isolated SQLite migration/backfill validation without touching the configured database.

## Implementation details

- Migration `0012_mobile_phone_evidence_and_raw_retention` canonicalizes legacy mobiles, backfills phone/evidence rows, and schedules raw-response expiry timestamps. Migration `0013_businessphone_permission_confirmed_at_and_more` adds auditable marketing-permission evidence. Both migrations were applied against a temporary SQLite database containing legacy mobile and landline records; only the mobile was migrated and its evidence/retention metadata were verified.
- Raw-response defaults are depth 12, node count 10,000, string limit 20,000 characters, response cap 65,536 bytes, and 90-day retention. Setting `SOURCE_RAW_RESPONSE_RETENTION_DAYS=0` disables raw payload storage. Celery Beat runs the purge task daily; the application web process alone does not execute scheduled cleanup.
- Successful business counts and regular result listings remain mobile-only. Non-mobile businesses remain stored for internal review and enrichment but are not counted as successful search results.
- No new package or provider credentials were added. No live provider calls were run because they are quota-limited and no live test target was supplied.

## Known dependencies and limits

- Existing MCP providers are the ones catalogued in `docs/SOURCE_CATALOG.md`; they are mostly unofficial integrations. Their live data, phone fields, public terms, regional access, and account-specific quotas vary. Provider schema checks are not evidence of mobile yield.
- General web search and official business-site fetch need explicit, bounded permissions. No search API credentials or configured legal provider were found during the initial repository audit.
- Marketing permission cannot be inferred from a mobile number being syntactically valid or publicly listed. The app must retain `unknown` unless supported evidence is recorded.
