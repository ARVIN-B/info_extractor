# SearXNG integration implementation plan

## Baseline and architecture

- [x] Read `docs/searxng_upate.md` completely and inspect the repository, providers, settings, output flow, and existing web tests.
- [x] Confirm the current architecture: parallel Neshan, Balad, Emalls, and web lanes; SearXNG discovers pages; Firecrawl crawls discovered sites; the existing Iranian-mobile regex and `JobContact` model provide normalization and phone-based deduplication.
- [x] Record baseline gap: SearXNG currently uses one query, no authentication, fixed language, no pagination, and default TLS settings; local `.env` still points to loopback rather than the documented service.
- [x] Attempt a strict-TLS authenticated live request to the documented endpoint; the development machine receives `ConnectError`, so a live response cannot be verified here.

## Implementation

- [x] Add safe SearXNG auth, HTTPS validation, configurable TLS CA/verification, timeout, language, enable flag, and page limit while preserving the existing `WEB_SEARCH_ENABLED` compatibility setting.
- [x] Add bounded transient retry, explicit 4xx/429/5xx and malformed-response handling, and persistent cooldown for HTTP 429.
- [x] Add deduplicated Persian/English, trade/location/contact queries with incremental `pageno` pagination and exact request accounting.
- [x] Preserve normalized URL, title, snippet, engine/date/score metadata through the existing web lane; do not treat a result as verified business data.
- [x] Improve phone/name/short-description/website extraction from SearXNG snippets and Firecrawl pages, while retaining phone-based deduplication and source evidence.
- [x] Add a manual `check_searxng` management command that uses the same configured client and never prints credentials.

## Verification and documentation

- [x] Add mocked tests for auth, TLS configuration, language, pagination, deduplication, empty/malformed responses, retries, errors, 429 cooldown, and extraction.
- [x] Run Django checks, migrations check, and the project test suite with `.venv` Python only.
- [x] Run the real provider check if this environment can reach the documented SearXNG server; report the actual result honestly.
- [x] Update `.env.example`, provider/service docs, README, and this checklist; do not edit `.env` or install packages.

## Production issue follow-up (2026-11-21)

- [x] Preserve strict TLS verification and document remediation for hostname/SAN mismatch and private CA deployment.
- [x] Enable SQLite WAL and configure a busy timeout; shorten cancellation writes and retry transient lock contention.
- [x] Run regression tests, Django checks, migration checks, and a live SearXNG check; record certificate limitation and verified cause (self-signed issuer, matching IP SAN).
