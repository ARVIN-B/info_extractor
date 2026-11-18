# Scale info_extractor to 1,000–5,000 Unique Business Leads

Repository: https://github.com/ARVIN-B/info_extractor

I want to evolve this project from a small-scale business lead extractor into a reliable, resumable, large-scale extraction system capable of collecting up to 5,000 unique business records per search job.

This is not just a request to increase the maximum result number. I want you to investigate the current architecture, identify all internal and external bottlenecks, propose a better extraction strategy, and implement the most reliable solution.

You should also think independently and challenge my assumptions. If you find a better approach than the one I describe, explain it and implement it if it is compatible with the project's goals.

---

## 1. Main Objective

The user can request between 1 and 5,000 unique businesses.

The system should:

- Make its best effort to reach the requested number.
- Search all selected and usable sources.
- Distribute the workload intelligently.
- Redistribute unused capacity from weak or exhausted sources to other sources.
- Continue searching while useful results are still available.
- Stop only when the requested target is reached or there is no reasonable way to discover more results.
- Preserve every successfully collected record, even if some sources fail.
- Never report that the target was reached if it was not.

Reaching 5,000 is a target, not a guarantee.

If only 1,700 genuinely available unique businesses can be discovered, the job should finish with those 1,700 records and a truthful explanation of why it stopped.

## 2. Current Allocation Problem

Review:

- `leads/sources.py`
- `leads/tasks.py`
- `leads/adapters.py`

The project currently has a `calculate_source_budget()` function that distributes the initial result target approximately equally across selected sources.

The current implementation is not sufficiently adaptive.

For example, suppose the user requests 3,000 unique businesses and selects six sources:

| Source | Initial allocation | Actual results |
|---|---:|---:|
| Neshan | 500 | 300 |
| Balad | 500 | 400 |
| Emalls | 500 | 100 |
| Basalam | 500 | 500 |
| Torob | 500 | 200 |
| Iran Jobs | Remaining | 1,500 |

This is only an illustrative example.

The problem is that unused capacity from early sources is not dynamically redistributed to the next available sources. The last source effectively receives most of the remaining target.

### Required behavior: Dynamic quota redistribution

Design a dynamic allocation mechanism.

My initial proposal:

1. Calculate the remaining unique-lead target.
2. Identify sources that are still eligible to search.
3. Divide the remaining target fairly between those sources.
4. Execute one source within its current allocation.
5. Count the number of genuinely new unique leads saved.
6. If the source is exhausted or cannot produce more results, redistribute its unused allocation.
7. Recalculate the remaining target and eligible source pool.
8. Continue until the requested target is reached or all usable sources are exhausted or blocked.

Important distinctions:

- A source returning fewer results than expected is not automatically a failure.
- A source that has no more pages or relevant records can be considered exhausted.
- A source that encounters HTTP 429 is temporarily blocked, not necessarily exhausted.
- A source that reaches an internal time or request budget should be resumable if it may have more data.
- A source that reaches its current allocation but has more pages should remain eligible for another round.

Do not simply give all unused results to the last source.

Consider a round-robin or weighted-fair scheduling strategy if it provides better behavior.

Equal allocation can be the initial policy, but redistribution must be dynamic.

You may also consider historical source performance (unique leads per search call, duplicate ratio, contact-field yield, failure rate) as an optional weighting mechanism. Do not make historical statistics a mandatory dependency for the first implementation.

### Critical counting rule

The target must be based on unique `BusinessLead` records, not raw MCP results.

For example, if Neshan and Balad both discover the same business, that business must count only once toward the requested target.

Deduplication must remain conservative. Do not merge unrelated branches just because they have similar names.

## 3. Investigate Every Existing Limit

I found the following limits in the current repository:

| Limit | Current value |
|---|---:|
| Maximum result count in `SearchJobForm` | 500 |
| Global MCP calls per job | 200 |
| MCP calls per source per job | 40 |
| Some adapter pagination limits | 5 pages |
| Celery hard task time limit | 900 seconds |
| Celery soft task time limit | 840 seconds |

These values are not all equivalent. Some are internal project settings, while others may reflect upstream service restrictions.

Investigate every relevant limit, including limits hidden inside individual adapters.

Specifically inspect:

- `leads/forms.py`
- `leads/models.py`
- `leads/adapters.py`
- `leads/mcp_client.py`
- `leads/sources.py`
- `leads/tasks.py`
- `config/settings.py`
- `.env.example`
- `README.md`

Also inspect any additional pagination, result truncation, timeout, retry, cache, and rate-limit logic.

Do not assume that changing `max_results` is enough.

## 4. Increase the Internal Result Target

I want the application to support up to 5,000 requested unique businesses.

Implement this consistently across:

- Django form validation.
- SearchJob model and migrations if required.
- Any API or view-level validation.
- Templates and frontend controls.
- Export functionality.
- Settings and environment variables.
- README and deployment documentation.

Requirements:

- Keep the default requested result count reasonable.
- Make the maximum configurable.
- Set a sensible production maximum of 5,000 by default.
- Avoid unnecessary database migrations if existing field types already support the new range.
- Validate input server-side, not only in HTML.
- Ensure JSON and Excel exports can handle 5,000 records without unnecessary memory or performance problems.

Do not silently allow an unlimited number of results.

## 5. Investigate and Redesign MCP Call Budgets

The current project has:

```text
SOURCE_MAX_CALLS_PER_JOB=40
MAX_MCP_CALLS_PER_JOB=200
```

These internal limits can prevent large extraction jobs from reaching their target.

I want you to evaluate whether the current fixed limits should be replaced with:

- Configurable global request budgets.
- Configurable per-source budgets.
- Per-task execution budgets rather than unnecessarily restrictive lifetime budgets.
- Separate search and detail request budgets.
- Dynamic redistribution of unused internal call allowances.
- A safe way to resume a source after reaching a temporary execution budget.

Do not just increase the numbers blindly.

Estimate how many MCP calls are realistically needed for 1,000 and 5,000 businesses, considering that some adapters make additional calls to retrieve seller or business profiles.

A particularly important issue:

Some sources require one search call, while others require multiple product, offer, seller, or detail calls.

A single global request limit does not necessarily represent the actual discovery capacity of each source.

Design the budget system around the actual behavior of each adapter.

Do not let one source consume the entire global request budget before other selected sources have a reasonable opportunity to run.

At the same time, unused capacity must become available to the remaining eligible sources.

## 6. Pagination and Exhaustive Discovery

Investigate every adapter individually.

Some adapters currently use a small fixed number of pages. Some may only request the first page.

I want the system to retrieve all reasonably accessible relevant results, not just the first few pages.

For each source:

1. Inspect the real MCP tool schema and supported pagination parameters.
2. Determine whether pagination uses page numbers, offsets, cursors, or another mechanism.
3. Determine the actual maximum page size.
4. Continue requesting pages while new useful records are being returned.
5. Stop when the source indicates there are no more results, pagination is exhausted, or repeated pages yield no new records.
6. Detect repeated pages and repeated record IDs.
7. Preserve results from earlier pages if a later page fails.
8. Record the last successfully processed page or cursor.
9. Resume from the saved position when a job continues.

Do not assume every MCP server supports the same pagination contract.

Do not invent unsupported parameters.

Use the actual live schema and the MCP server implementation where available.

For sources without pagination, investigate other legitimate search-query variations that are supported by that source.

## 7. Large-Scale Resumable Jobs

The current Celery task has a 15-minute hard execution limit.

A job collecting 5,000 records may take much longer.

I do not want the worker to attempt to perform the entire job in one uninterrupted task.

Design a resumable execution strategy.

My preferred direction is:

- Split a large job into manageable execution batches.
- Persist the progress of every source.
- Save pagination cursors, page numbers, query variants, and other necessary state.
- Resume the job through Celery continuation tasks.
- Preserve previously collected records.
- Avoid processing the same page repeatedly after a worker restart.
- Make execution idempotent.
- Recover safely if a worker crashes or is terminated.
- Respect job cancellation.
- Never mark a job completed while more eligible work remains.

Review the existing stale-job recovery mechanism in `leads/tasks.py` before implementing anything.

If necessary, introduce persistent fields in `SourceExecution`, such as a JSON pagination/checkpoint state.

Do not introduce duplicate task scheduling or infinite continuation loops.

The job must have a reliable terminal condition.

## 8. Handle Rate Limits Properly

This part is especially important.

I want you to investigate ways to improve the practical collection capacity when sources impose request limits.

However, distinguish between internal application limits and actual upstream restrictions.

### Allowed improvements

Implement or propose:

- Respecting `Retry-After` and provider-provided reset times.
- Persistent per-source cooldowns.
- Exponential backoff with jitter for transient failures.
- Redis-based coordination across workers.
- Request spacing where required.
- Caching repeated search and detail responses.
- Avoiding duplicate API calls.
- Resuming jobs after daily or monthly quota resets when the provider gives a reliable reset time.
- Separating temporary rate-limit states from permanent failures.
- Using official APIs, valid credentials, or commercial access agreements when available.
- Making source-specific concurrency and request policies configurable.

### Do not implement

- IP rotation intended to evade a provider's rate limits.
- CAPTCHA bypass.
- Authentication or access-control bypass.
- Hidden request behavior intended to avoid detection.
- Repeated requests that ignore a provider's cooldown.
- Any mechanism that falsely reports success after an upstream service refuses access.

If an upstream provider has a strict daily or monthly quota, the system must report that limitation honestly and resume when legitimately possible.

**I want you to investigate whether any of the current MCP providers offer official API access, higher usage tiers, or commercial quota arrangements. Do not assume they do.**

## 9. Search Coverage and Geographic Partitioning

Investigate the current geographic search strategy in `leads/sources.py`.

For Iran-wide searches, the project currently uses a predefined set of city centers.

Determine whether this is sufficient for large-scale collection.

Evaluate:

- More complete city coverage.
- Province-based partitions.
- Geographic grid or radius-based partitioning where the source supports it.
- Overlapping search areas.
- Query variations and synonyms.
- Source-specific geographic capabilities.
- Avoiding repeated results across nearby geographic partitions.

If a geographic grid is implemented:

- Keep its parameters source-specific.
- Avoid creating excessive overlapping requests.
- Deduplicate records across adjacent areas.
- Persist the areas already searched.
- Resume incomplete geographic partitions.
- Do not claim nationwide exhaustive coverage if the underlying source does not provide it.

For a city search, do not unnecessarily expand to other cities.

For a province search, preserve the province boundary as much as the available source data allows.

For an Iran-wide search, use the best legitimate coverage available from each source.

## 10. Separate Discovery From Detail Enrichment

Investigate whether every discovered business needs an immediate detail request.

Some adapters may perform:

- Search.
- Product lookup.
- Seller offer lookup.
- Business profile lookup.

Other sources may return useful public contact information directly.

I want you to evaluate a two-stage approach:

**Stage A — Discovery**

- Find businesses.
- Save stable source IDs.
- Save the available public business information.
- Deduplicate immediately.
- Prioritize reaching the requested number of unique businesses.

**Stage B — Enrichment**

- Fetch additional public details when useful.
- Prioritize businesses with missing phone numbers, websites, emails, or other important fields.
- Avoid repeated profile requests.
- Use cached details.
- Keep enrichment failures separate from discovery failures.

Do not sacrifice discovery capacity by making unnecessary detail calls for every result.

However, preserve the existing evidence model and field-level provenance.

Do not fabricate missing contact information.

## 11. Performance and Database Scalability

Inspect the current deduplication and persistence implementation.

In particular, review `_find_match()` and `save_lead()` in `leads/sources.py`.

Check whether repeated database queries and Python-level iteration become expensive when a job contains thousands of records.

Evaluate:

- Appropriate database indexes.
- Efficient lookup by source IDs.
- Efficient lookup by normalized phone, website domain, and national ID.
- Reusable in-memory deduplication indexes during a job.
- Bulk operations where they do not compromise evidence integrity.
- Transaction boundaries.
- Avoiding N+1 queries.
- SQLite write contention.
- PostgreSQL suitability for production workloads.

The current conservative deduplication behavior must remain correct.

Do not replace it with aggressive fuzzy matching that merges unrelated businesses.

If an in-memory index is introduced, ensure it is updated whenever a new lead is inserted or merged.

## 12. Source Health and Intelligent Scheduling

A source should have a meaningful state.

Consider distinguishing:

- Active and producing results.
- Active but temporarily returning no results.
- Exhausted: no more relevant pages or query variations.
- Rate limited.
- Long cooldown.
- Temporarily unavailable.
- Failed due to a permanent configuration or schema problem.
- Paused because of an internal execution budget.
- Completed successfully.

The scheduler should use these states when deciding where to allocate remaining work.

Do not treat every zero-result response as proof that a source is exhausted.

Do not repeatedly call a source that is already under a known cooldown.

Keep the existing independent-source error handling and fallback behavior.

## 13. Monitoring and User Feedback

A 5,000-result job may take a long time.

Improve the job status/reporting if necessary.

I want the user to understand:

- Requested unique businesses.
- Current unique businesses collected.
- Remaining target.
- Raw results discovered.
- Requests made per source.
- Unique leads contributed by each source.
- Current source status.
- Pages or geographic areas processed.
- Whether the source has more work available.
- Whether the source is rate-limited.
- Whether the job is waiting for a cooldown.
- Whether the job is continuing in another Celery batch.
- Why the job eventually stopped below its requested target.

Keep the existing Persian RTL interface.

Avoid showing misleading progress percentages when the total number of available businesses is unknown.

A message such as "1,450 of 5,000 requested; continuing discovery" is more honest than pretending that 29% of all available businesses have been found.

## 14. Testing Requirements

Add comprehensive tests using mocked MCP responses. Automated tests must not depend on live websites.

Test at least:

### Allocation
- Equal initial allocation.
- Redistribution when a source is exhausted early.
- Redistribution across multiple remaining sources.
- A source that has more pages after its first allocation.
- All sources exhausted before reaching the target.
- Duplicate records across sources.
- No allocation to a permanently failed or currently rate-limited source.
- A temporarily paused source becoming eligible again.

### Pagination
- Multiple pages.
- Empty final page.
- Repeated pages.
- Duplicate IDs across pages.
- Failure on a later page with earlier results preserved.
- Correct resumption from a checkpoint.

### Large jobs
- 1,000 requested results.
- 5,000 requested results.
- Continuation after a Celery execution time limit.
- Worker restart.
- Job cancellation during continuation.
- No duplicate leads or duplicate continuation loops.

### Rate limits
- HTTP 429 with short Retry-After.
- HTTP 429 with long Retry-After.
- Daily quota exhaustion.
- Monthly quota exhaustion.
- Resume after cooldown.
- Other sources continuing while one source is rate-limited.

### Persistence and performance
- Deduplication across sources.
- Evidence preservation.
- Source ID persistence.
- Correct counters after continuation.
- Export of more than 500 results.
- Reasonable database query performance.

Run the full existing test suite as well as the new tests.

## 15. Important Constraints

Preserve the project's existing core architecture:

- Django.
- Celery.
- Redis.
- MCP Python SDK over STDIO.
- Independent source adapters.
- Field-level evidence.
- Conservative deduplication.
- Public business contact information only.
- JSON and Excel exports.
- Per-source error isolation.

Do not unnecessarily rewrite the entire application.

Do not remove existing sources or silently disable difficult sources.

Do not hardcode provider assumptions.

Do not change working MCP tool arguments without verifying their real schemas.

Do not make a single source responsible for filling the entire target if other sources can contribute.

Do not confuse raw results with unique business leads.

## 16. Your Independent Technical Assessment

Before implementing the changes, I want you to independently assess the architecture.

Answer these questions:

1. Is dynamic equal redistribution the best allocation strategy, or would weighted scheduling be more effective?
2. Should result quotas and MCP request quotas be managed separately?
3. Should search and detail enrichment be separate execution stages?
4. Which adapters currently have insufficient pagination?
5. Which providers are likely to become the main bottlenecks at 1,000 and 5,000 results?
6. Which current internal limits are unnecessarily restrictive?
7. What are the most likely performance bottlenecks in the current database and deduplication implementation?
8. Is the current Celery continuation and stale-job recovery mechanism sufficient?
9. What is the safest way to resume after a provider's daily or monthly quota is exhausted?
10. What changes would you make to keep the system reliable when several large jobs are running?

I want you to provide your proposed architecture and reasoning before implementation.

Then implement the best solution, using the smallest reasonable set of architectural changes.

## 17. Final Deliverables

After implementation, provide:

1. A summary of the original bottlenecks.
2. Your proposed architecture and why you chose it.
3. A list of modified and newly created files.
4. Any database migrations.
5. New or changed environment variables.
6. A description of the dynamic allocation algorithm.
7. A description of pagination and checkpoint/resume behavior.
8. A description of rate-limit and quota handling.
9. Test results.
10. Any limitations that still depend on upstream providers.
11. Updated README documentation.
12. Recommended production settings for 1,000 and 5,000 result jobs.
13. Exact deployment and migration commands.

Do not claim that the system can always produce 5,000 results. The objective is to make the system exhaust its legitimate discovery opportunities efficiently and reliably before declaring that fewer results are available.

**Important:** Do not stop after changing the form's maximum from 500 to 5,000. This task is about making the complete extraction pipeline capable of handling large, long-running, resumable jobs.