# New Update 6 implementation plan and evidence

Date: 2026-11-19

## Baseline

- [x] Read `docs/new_update6.md` completely.
- [x] Confirm starting Git status: only `docs/new_update6.md` was untracked.
- [x] Inspect transport/decoder, source registry and installed schemas, adapters, extraction, persistence, UI/export, budgets, checkpoints, and cancellation paths.
- [x] Use project `.venv` for Python commands; install no packages; do not change `.env` or migrate the configured application database.

## Findings

- [x] All ten enabled MCP servers returned live tool schemas. Full captured schemas and representative responses are in `MCP_PLATFORM_RESPONSE_SAMPLES.md`.
- [x] Confirmed data loss: the MCP decoder previously preferred structured content and discarded accompanying text blocks.
- [x] Confirmed data loss: marketplace adapters persisted only the individual seller offer and omitted the full search/detail responses from phone extraction evidence.
- [x] Confirmed a correctness risk: scanning an entire multi-seller response could assign one seller's phone to another seller. Seller-scoped extraction now requires a matching seller identifier.
- [x] Confirmed overbroad identifier filtering could drop phone-shaped values under legitimate fields and nested objects; filtering is now precise for identifier leaves.
- [x] Live samples: Neshan, Balad, Emalls, Basalam, Rasmio search, Iran Jobs, Quera, Digikala, and SnappShop. Torob schema succeeded; one search timed out at its 15-second server limit and was not retried. Rasmio profile detail was not called due guest quota.
- [x] The captured Persian response text was mojibake. The review report preserves response keys/types but labels corrupted text instead of pretending it is readable.

## Implementation

- [x] Preserve MCP `structuredContent` and parsed text content together.
- [x] Preserve complete relevant search, detail, product, offer, shop/vendor, company, and profile responses in bounded raw evidence.
- [x] Extract marketplace phone values only from the offer or nodes matched to the current seller identifier.
- [x] Exclude phone candidates in account-like private contexts; explicitly public-contact branches remain eligible. Redact private profile values from retained raw responses.
- [x] Record source-level response, record, traversal, candidate, filtering, normalization, persistence, suppression, and mobile-yield diagnostics.
- [x] Attribute newly discovered businesses and created mobile rows to the search query variant.
- [x] Surface source diagnostics in job detail and JSON exports.
- [x] Add migration `0014_sourceexecution_diagnostics` and document the release migration step.
- [x] Keep current source budgets, pacing, cooldowns, query variants, geographic subdivision, resumable checkpoints, cancellation, and bounded Celery work. No increase to provider request limits or concurrency was justified by the evidence.
- [x] Add offline regression tests for MCP structured+text content, nested/Pydantic extraction, private-account filtering/redaction, marketplace complete payload retention, seller isolation, and query-variant yield accounting.

## Verification

- [x] Create one source-by-source live schema/sample report, with phone/email/private-profile redaction and explicit unavailable/timeout states.
- [x] Run full project tests, Django checks, migration drift checks, package consistency, compile check, and diff whitespace check.
- [x] Review final diff for secrets, unmasked contact data, unintended `.env` edits, and temporary sample files.
- [x] Remove local capture/build temporary files after final report generation.

## Limitations and release

- The live probes are small samples and do not prove that a provider never publishes a phone. Only provider response keys observed in this capture are stated.
- Torob search behavior remains unverified because the tool timed out. Rasmio profile details remain unverified because the guest quota discouraged another call.
- Country-wide geographic coverage remains budgeted over the existing finite set of city centers; this is not exhaustive national coverage.
- Run `python manage.py migrate` during release to add source diagnostics. No Python package change is required.

## Final status

- Implementation: complete; all local verification commands passed.
- Live source capability report: captured and privacy-redacted, with per-source evidence limits.
- Production provider-wide contact coverage: not claimed; providers control which public business contact fields they return.
