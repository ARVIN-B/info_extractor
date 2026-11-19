# Deep Audit & Implementation: Fix Mobile Phone Extraction, MCP Data Loss, Source Coverage and Search Yield

Repository:
https://github.com/ARVIN-B/info_extractor

## 1. Project Goal

The primary goal of this project is to discover businesses in Iran and extract their publicly available business mobile phone numbers.

The target is to collect approximately 1,000–5,000 unique business records, depending on the requested limit and actual source availability.

Mobile numbers are the most important output. Landline numbers are not useful for the primary objective.

The accepted Iranian mobile formats include:

- 11 digits starting with `09`
- 10 digits starting with `9`
- 12 digits starting with `98`
- 13 digits starting with `+98`
- Numbers containing parentheses, spaces, hyphens, or other common separators between digits.
- Persian and Arabic numerals.

All valid numbers should be normalized to E.164 format, such as `+989123456789`.

**Most importantly: I suspect the biggest problem is not the phone-number regex itself. It may be that the application is requesting the wrong data, using incorrect MCP parameters, discarding nested response fields, or passing incomplete objects to the extraction engine.**

I want a complete investigation, not a superficial fix.

## 2. Previous Execution Results

In one restaurant search, the application reported:

- 1,683 raw results.
- Only 17 businesses with mobile numbers.
- Approximately 1.01% mobile-bearing businesses.
- 11 mobile numbers from Emalls.
- 4 from Balad.
- 2 from Neshan.
- Zero mobile numbers from Basalam, Digikala, SnappShop, Torob, Rasmio, and Iran Jobs.

The execution was cancelled, so this was not a completed search.

Nevertheless, the results are suspiciously low.

My concern is particularly about Digikala, SnappShop, Torob, Basalam, and Iran Jobs.

These platforms have user, vendor, shop, or company information associated with their records. However, the application consistently reports zero mobile numbers from several of them.

This raises an important question:

**Are the phone numbers actually absent from the MCP responses, or is our application failing to retrieve, preserve, traverse, or recognize them?**

Do not assume either possibility. Prove it using actual response schemas and representative test payloads.

Also distinguish between publicly available business contact information and private account phone numbers. Do not attempt to expose private user data or bypass authentication, access controls, privacy restrictions, or provider limitations.

## 3. Highest Priority: Audit the Entire Phone Retrieval Pipeline

Investigate the complete data flow:

MCP tool schema
→ MCP arguments
→ MCP response
→ response parsing
→ adapter transformation
→ raw response preservation
→ recursive phone extraction
→ normalization
→ validation
→ evidence storage
→ BusinessLead persistence
→ UI and Excel export.

At every stage, determine whether phone-related information can be lost.

### 3.1. Inspect every MCP tool schema

For every enabled source, inspect the actual installed MCP server and its live `list_tools()` output.

Do not rely solely on the source catalog or assumptions about field names.

For each tool, document:

- Exact tool name.
- Required parameters.
- Optional parameters.
- Parameter types.
- Search parameters.
- Shop, vendor, seller, company, or profile identifiers.
- Detail/profile retrieval parameters.
- Actual response structure.
- Nested objects containing public business contact information.
- Pagination and result limits.
- Whether the tool provides public phone information at all.

Pay special attention to:

- `ns_search` and `ns_place`
- `bl_search`, `bl_nearby`, and `bl_place`
- `em_search`, `em_offers`, `em_shop`, and `em_shops`
- `bs_search` and `bs_vendor`
- `tb_find_shops`
- `dk_search` and `dk_product`
- `ss_search` and `ss_product`
- `job_companies`
- `qr_companies` and `qr_company`
- `rs_search_companies`

Verify that the application sends the correct identifier to every detail endpoint.

For example, do not confuse:
- product ID
- shop ID
- seller ID
- vendor ID
- company ID
- profile slug.

A successful search request does not prove that the subsequent detail request is correct.

### 3.2. Investigate MarketplaceProductAdapter

This is one of the most important areas.

In `leads/adapters.py`, inspect `MarketplaceProductAdapter.discover()`.

The current implementation obtains a product detail response, extracts seller offers, and then creates records using:

`row = dict(offer, ...)`

`found.append((row, offer))`

This potentially discards the original complete product-detail response.

For example, the actual response might look conceptually like this:

```json
{
  "product": {
    "id": 123
  },
  "seller": {
    "id": 456,
    "user": {
      "phone": "09123456789"
    }
  },
  "offers": [
    {
      "seller_id": 456,
      "seller_name": "Example Store"
    }
  ]
}
```

If the adapter only forwards the individual offer, information elsewhere in the original response is lost.

The example is illustrative; inspect the actual provider schemas and responses.

Investigate this for both Digikala and SnappShop.

Implement a solution that:

1. Preserves the entire original detail response.
2. Preserves the original search result.
3. Preserves the individual seller offer.
4. Preserves any available public seller/profile information.
5. Makes all relevant public business-contact data available to the recursive extractor.
6. Maintains the correct relationship between each seller and its phone evidence.

Do not simply attach the entire product response to every seller and accept every number found. A number must be attributable to the correct seller/business.

If the same product contains multiple sellers, do not accidentally associate one seller's number with another seller.

Apply the same full-payload audit to Emalls, Basalam, Quera, Torob, and Iran Jobs.

### 3.3. Audit `_source_raw` and response preservation

In `leads/sources.py`, inspect `_field_values()`.

Currently:

`search_raw = search_record.get("_source_raw", search_record)`

This means `_source_raw`, when present, replaces the complete search record for extraction purposes.

Investigate whether adapters are creating incomplete `_source_raw` objects.

For every adapter, compare:

- Original MCP search response.
- Original MCP detail response.
- Transformed business record.
- `_source_raw`.
- Actual input passed to `extract_iranian_mobiles()`.

Ensure that no relevant public business-contact information is discarded during transformation.

Preserve complete relevant source payloads, subject to safe size and retention limits.

Also inspect `_safe_source_response()`.

Verify that structural depth, node-count, string-length, and byte-size limits do not silently remove important contact information before extraction.

If truncation occurs, record it explicitly.

Phone extraction should ideally happen on the original response before any storage-oriented truncation.

### 3.4. Audit recursive extraction and identifier filtering

Inspect `leads/normalization.py`.

In particular:

- `_is_identifier_key()`
- `_has_contact_context()`
- `extract_iranian_mobiles()`
- `_MOBILE_PATTERN`
- `normalize_phone()`
- `normalize_iranian_mobile()`

I want the extractor to inspect every relevant nested public business-data field, regardless of whether its key is named:

- phone
- mobile
- telephone
- contact
- user
- customer
- seller
- vendor
- shop
- company
- profile
- account
- owner
- details
- metadata
- data
- information
- any other provider-specific field.

These are examples, not an exhaustive list.

Do not depend on known phone-related key names.

However, examine `_is_identifier_key()` carefully.

It currently excludes a value when its parent key contains certain identifier-related substrings, including `id`.

Check whether this logic excludes legitimate contact data accidentally.

Replace overly broad substring-based filtering with precise identifier detection.

For example, avoid treating an entire nested object as irrelevant merely because its key contains an identifier-related word.

The extractor should:

- Traverse nested dictionaries and lists.
- Handle Pydantic objects.
- Handle JSON strings embedded inside fields.
- Handle Unicode Persian and Arabic digits.
- Handle common phone separators.
- Avoid matching portions of longer unrelated numbers.
- Avoid extracting order IDs, postal codes, product IDs, national IDs, or unrelated identifiers as phones.
- Deduplicate normalized numbers.
- Preserve the exact field path and source of each candidate.
- Continue to respect configurable resource limits.

Do not reduce extraction coverage to improve performance.

### 3.5. Important: Inspect actual MCP response serialization

Inspect `leads/mcp_client.py` and determine exactly how tool responses are converted into Python objects.

Check:

- `structuredContent`
- `structured_content`
- Text content blocks.
- JSON-encoded text blocks.
- Lists of content blocks.
- Nested response envelopes.
- Pydantic models.
- Unexpected object types.

Determine whether phone-bearing data can exist in a response representation that the current `.data` handling ignores.

If necessary, implement a consistent response-unpacking layer that preserves all relevant structured public data without treating arbitrary text or errors as successful records.

## 4. Source-by-Source Investigation

Create a detailed audit table for every source.

| Source | Search result | Detail/profile | Public mobile availability | Extractor coverage |
|---|---|---|---|---|
| Neshan | Inspect | Inspect | Verify | Test |
| Balad | Inspect | Inspect | Verify | Test |
| Emalls | Inspect | Inspect | Verify | Test |
| Basalam | Inspect | Inspect | Verify | Test |
| Torob | Inspect | Inspect | Verify | Test |
| Digikala | Inspect | Inspect | Verify | Test |
| SnappShop | Inspect | Inspect | Verify | Test |
| Iran Jobs | Inspect | Inspect | Verify | Test |
| Quera | Inspect | Inspect | Verify | Test |
| Rasmio | Inspect | Inspect | Verify | Test |

For each source, answer:

1. Does the search endpoint return phone information?
2. Does the detail endpoint return additional public phone information?
3. Is there another public profile endpoint that the current implementation does not use?
4. Are we passing the correct identifier?
5. Are we passing all required parameters?
6. Are we discarding part of the response?
7. Does the response parser understand the actual output format?
8. Does recursive extraction inspect the complete relevant response?
9. Are numbers being rejected by normalization?
10. Is the provider actually withholding the phone number?

If a source does not publicly expose a business phone number, document that fact instead of inventing a workaround.

For Rasmio, specifically examine whether its search-only strategy is appropriate and whether any additional public information can be obtained without repeatedly consuming restricted guest profile quotas.

For marketplace platforms, distinguish between a public seller business-contact field and a private account registration number.

## 5. Build a Phone Extraction Diagnostic System

I want this project to become observable enough that we can identify exactly where phone numbers disappear.

For each source and execution, record:

- Number of search records received.
- Number of detail records received.
- Number of complete raw payloads inspected.
- Number of nested objects traversed.
- Number of strings inspected.
- Number of phone-like candidates found.
- Number of valid Iranian mobile candidates.
- Number of rejected candidates.
- Number of candidates rejected by identifier filtering.
- Number of candidates rejected by normalization.
- Number of unique normalized mobiles.
- Number of mobiles persisted.
- Number of records with no public mobile available.

Also record the source field path for every candidate.

For example:

`source=digikala`
`record_id=...`
`field_path=...`
`raw_candidate=...`
`normalized=...`
`validation_status=...`

Avoid exposing complete phone numbers in ordinary application logs. Mask them where appropriate.

The diagnostic system should allow me to distinguish these situations:

- The provider returned no phone.
- The provider returned a phone but the adapter discarded it.
- The phone was present but the parser missed it.
- The extractor found it but normalization rejected it.
- The phone was valid but database persistence failed.
- The number was already associated with an existing business.
- The number was suppressed or excluded by policy.

Do not report a source as having zero available phones just because extraction returned zero candidates.

Distinguish `not_provided`, `not_found`, `not_checked`, `invalid`, and `rate_limited` accurately.

## 6. Add Comprehensive Automated Tests

Create offline fixtures representing the actual response structures of every integrated MCP source.

At minimum, test:

1. Phone directly inside the response.
2. Phone inside a nested user object.
3. Phone inside a nested seller object.
4. Phone inside a vendor profile.
5. Phone inside a company profile.
6. Phone inside a list of contacts.
7. Phone inside a JSON-encoded string.
8. Phone inside a Pydantic object.
9. Persian digits.
10. Arabic digits.
11. Numbers with parentheses.
12. Numbers with hyphens.
13. Numbers with spaces.
14. Numbers beginning with `09`.
15. Numbers beginning with `9`.
16. Numbers beginning with `98`.
17. Numbers beginning with `+98`.
18. Invalid numbers.
19. Unrelated identifiers.
20. Multiple sellers with different contact information.
21. A phone in the original product-detail response but outside the seller-offer object.
22. A phone in the detail response but not the search response.
23. A phone in the search response but not the detail response.
24. Truncated payloads.
25. Duplicate numbers across sources.

Most importantly, create regression tests specifically proving that the complete original MCP response survives adapter transformation.

Do not use fabricated test fixtures as evidence that an upstream provider actually exposes a particular phone field. Separate parser tests from live provider capability tests.

## 7. Reassess Source Selection and Search Quality

The project should prioritize sources that are useful for discovering actual businesses and their publicly available business contact information.

For a restaurant search, prioritize local business discovery sources such as:

- Balad
- Neshan

Then investigate other relevant public business sources.

Marketplace sources can be valuable for online stores but should not automatically receive the same priority as local business directories for a restaurant search.

Review the source catalog and its metadata.

Create a source relevance and contact-yield strategy based on:

- Business category compatibility.
- Geographic coverage.
- Actual number of records returned.
- Public mobile yield.
- Detail endpoint availability.
- Request cost.
- Rate limits.
- Reliability.

Do not permanently disable a source just because one execution returned zero phones.

A source may still contain valuable records or useful public business information.

## 8. Fix Result Allocation and Geographic Coverage

The requested result limit should represent the target number of unique businesses with valid public mobile numbers, not merely raw search records.

The system should:

- Distribute initial search effort across relevant sources.
- Dynamically redistribute unused capacity when a source returns fewer results than expected.
- Give additional opportunities to sources that demonstrate better contact yield.
- Continue searching when a source produces no mobile numbers, provided more useful queries or pages remain.
- Avoid spending excessive resources on sources with poor relevance.
- Deduplicate businesses and numbers across sources.
- Preserve all valid results already collected.

Investigate `calculate_source_budget()`, `calculate_source_call_allowance()`, `_search_source()`, and `_search_catalog_source()`.

Check whether source reservations or global call budgets prevent useful sources from continuing after other sources have returned zero results.

For country-wide searches, inspect the geographic strategy carefully.

The current code has 23 predefined city centers.

Determine whether this is sufficient for a country-wide search and whether dividing a source budget across 23 cities creates unnecessarily small per-city limits.

Improve geographic coverage through adaptive allocation and pagination.

The target is maximum useful coverage, not merely completing a fixed number of API calls.

## 9. Fix Search Cancellation and Long-Running Jobs

The previous execution was cancelled.

Investigate whether this happened because of:

- Too many sequential detail requests.
- Excessive per-record processing.
- Slow MCP calls.
- Unnecessary repeated searches.
- Celery execution limits.
- Worker configuration.
- Internal request budgets.
- UI polling or timeout behavior.

Implement:

- Efficient asynchronous processing where safe.
- Controlled concurrency.
- Bounded parallel detail retrieval.
- Persistent checkpoints.
- Reliable resume behavior.
- Preservation of partial results.
- Accurate progress reporting.
- Safe cancellation.

Do not make Neshan or Balad detail requests faster than their configured or provider-required limits.

Do not use aggressive retries.

## 10. Request Limits and Provider Restrictions

I previously asked for a way to increase the number of results, but I do not want the application to bypass provider restrictions.

Do not implement:

- CAPTCHA circumvention.
- Authentication bypass.
- Unauthorized access to private account data.
- Automatic proxy rotation to evade rate limits.
- Aggressive retry loops.
- Techniques that violate provider terms.

Instead, maximize legitimate coverage through:

- Pagination.
- Query variation.
- Geographic subdivision.
- Caching.
- Deduplication.
- Adaptive source selection.
- Respectful scheduling.
- Persistent cooldown handling.
- Additional permitted public data sources.

If an upstream quota is genuinely exhausted, record it and resume when permitted.

## 11. Improve Search Query Expansion

Keep the existing LLM-based query expansion system, but audit whether its output actually reaches every source adapter.

Use source-compatible search variants.

For restaurants, for example, variants might include:

- رستوران
- غذاخوری
- سفره خانه
- رستوران سنتی
- فست فود
- کترینگ

These are examples, not instructions to send every phrase to every provider.

Avoid irrelevant queries and duplicated results.

Measure the additional unique businesses and mobile numbers contributed by each variant.

## 12. Improve Database and Export Behavior

Make sure a business is not discarded simply because it has no mobile number in its first source.

A business may receive a public mobile number from another source or a later enrichment step.

Keep useful business records and their evidence.

However, distinguish clearly between:

- Businesses discovered.
- Businesses with public mobile numbers.
- Businesses with only landlines.
- Businesses without contact information.
- Businesses with invalid contact candidates.

The primary result count should remain the number of unique businesses with valid public mobiles.

Provide separate diagnostic counts for all discovered businesses.

Preserve source provenance and field-level evidence.

Make sure Excel export contains only appropriate public business-contact data.

## 13. Performance and Architecture

Do not solve the problem by indiscriminately increasing all limits.

Profile the actual bottlenecks.

Investigate:

- Number of MCP calls per business.
- Average search latency.
- Average detail latency.
- Database query count.
- JSON parsing cost.
- Duplicate processing.
- Repeated profile retrieval.
- Cache effectiveness.
- Celery task duration.

Implement improvements without compromising data correctness.

## 14. Required Implementation Workflow

I want you to approach this as a collaborative engineering investigation.

### Phase A: Independent analysis

Before modifying code:

1. Independently analyze the problem.
2. Inspect the entire relevant code path.
3. Identify potential data-loss points.
4. Inspect actual MCP schemas.
5. Determine which sources genuinely expose public business contact information.
6. Rank the bugs by impact and confidence.
7. Present your findings and proposed implementation strategy.

Do not blindly follow my hypothesis. Challenge it if the evidence indicates another cause.

### Phase B: Implement the fixes

After identifying the causes:

1. Fix incorrect parameter mappings.
2. Fix response parsing.
3. Preserve complete relevant source responses.
4. Fix adapter-level data loss.
5. Improve recursive extraction.
6. Fix false-negative normalization.
7. Improve diagnostics.
8. Improve source allocation.
9. Improve geographic coverage.
10. Improve performance and checkpointing.

Prioritize phone retrieval and preservation over cosmetic changes.

### Phase C: Verify

Run all offline tests.

Then perform controlled live checks against sources where permitted.

For each source, report:

- Search tool success.
- Detail tool success.
- Actual returned data structure.
- Public phone fields observed.
- Candidate count.
- Valid mobile count.
- Extraction success rate.
- Any upstream limitations.

Compare results before and after implementation.

Do not claim that the problem is solved merely because tests pass.

### Phase D: Deployment

Check:

- Django system checks.
- Database migrations.
- Celery configuration.
- Production dependencies.
- Environment variable compatibility.
- Existing data compatibility.
- Excel export.
- Job resume and cancellation.

Do not overwrite the user's existing `.env` configuration.

## 15. Acceptance Criteria

The implementation is not complete until:

1. Every enabled source has been individually audited.
2. Every adapter preserves the relevant original source payload.
3. Nested public business phone information is discoverable.
4. No phone-bearing response fields are silently discarded.
5. The marketplace detail-response regression is tested.
6. Number normalization is tested against all accepted formats.
7. Invalid identifiers are not accepted as mobile numbers.
8. Phone evidence records the exact source and field path.
9. Multiple sellers cannot inherit one another's phone numbers.
10. Existing valid records remain intact.
11. Source budgets are dynamically and sensibly allocated.
12. Search can resume after interruption.
13. Provider rate limits are respected.
14. All relevant tests pass.
15. Production deployment instructions are documented.

## 16. Final Report Required

After implementation, provide a detailed report containing:

1. Root causes discovered.
2. Which of my hypotheses were correct.
3. Which hypotheses were incorrect.
4. Exact files changed.
5. Exact functions changed.
6. Bugs fixed.
7. Tests added.
8. Test results.
9. Live MCP verification results.
10. Before/after extraction metrics.
11. Remaining limitations.
12. Recommended next steps.

**One final and very important point:**

I do not want a solution that simply searches more businesses while continuing to miss the phone numbers already present in the responses.

My highest priority is to ensure that every relevant public business-contact field returned by each MCP source actually reaches the phone extraction engine.

First prove that the data is being retrieved and preserved correctly. Then optimize coverage and performance.

Think independently, challenge assumptions, and choose the most reliable implementation based on evidence.