# Task: Build a production-minded Iranian Business Contact Discovery System using Django and iran-mcp

Act as a senior Python/Django engineer. I need you to implement a working, deployable MVP of an Iranian business discovery and contact extraction system.

GitHub repository for the MCP sources:
https://github.com/sepehr071/iran-mcp

## 1. Product objective

The user enters:
- A business category / trade (صنف), e.g. طلافروشی، رستوران، املاک، کلینیک
- A geographical scope: city, province, or all Iran
- The sources to search
- An optional maximum result count

The system searches relevant Iranian services through selected MCP servers from iran-mcp, collects publicly available business information, normalizes and deduplicates results, stores them, and provides Excel and JSON downloads.

This is an internal business research and advertising lead-generation tool.

This is NOT a SaaS platform. Do not build unnecessary multi-tenancy, subscription, payment, billing, or complex user-management features.

## 2. Important architectural decisions

- Use Django and Django Templates.
- Use PostgreSQL if the existing project already uses it. Otherwise inspect the current database setup before changing anything.
- Use Celery and Redis for long-running search jobs. Reuse existing infrastructure if available.
- Do NOT introduce n8n.
- Do NOT introduce React, Vue, or another frontend framework.
- Do NOT introduce an LLM or AI Agent into the data collection pipeline.
- Do NOT ask an LLM to generate JSON, extract contact details, validate phone numbers, or decide whether records are duplicates.
- Use deterministic Python code and actual MCP tool responses.
- Use the official Python MCP client SDK to communicate with MCP servers over STDIO.
- Do not treat `npx skills add` or Codex Agent Skills installation as a runtime MCP connection. Django must have its own real MCP client implementation.
- Do not install all 77 MCP servers. Install and enable only the relevant ones.

## 3. First inspect the repository

Before changing code:

1. Inspect the existing Django project, settings, installed apps, database, Celery configuration, Redis configuration, deployment setup, and current templates.
2. Determine whether this is an existing project or a new project.
3. Inspect the iran-mcp repository README, `servers.json`, `TOOLS.md`, and the individual README/source code of the selected MCP packages.
4. Verify the actual PyPI package names, available versions, tool names, argument schemas, return structures, environment variables, and runtime requirements.
5. Do not invent tool parameters. Discover and use the real schemas.
6. Produce a short implementation plan and then implement it. Do not stop after writing a plan.

Preserve existing project conventions and avoid unnecessary refactoring.

## 4. Initial MCP source selection

Implement the following sources as independent, configurable connectors:

### Maps
- `neshan-mcp`
  - `ns_search`
  - `ns_place`
- `balad-mcp`
  - `bl_search`
  - `bl_place`

### Company registry
- `rasmio-mcp`
  - `rs_search_companies`
  - `rs_company`

### Job platforms
- `iran-jobs-mcp`
  - Relevant company search and company profile tools from IranTalent, Jobinja, and Jobvision.
  - Use job-search tools only when they help discover a business.

### Classifieds
- `divar-mcp`
  - `dv_search`
  - `dv_post`
  - `dv_dealer`
- `sheypoor-mcp`
  - `sp_search`
  - `sp_ad`

### Online sellers
- `basalam-mcp`
  - `bs_search`
  - `bs_vendor`
- `emalls-ir-mcp`
  - `em_shops`
  - `em_shop`

Important:
- Inspect the actual schemas and descriptions before implementing calls.
- Some sources are only relevant to particular business categories.
- Do not pretend that every source provides every type of business.
- Do not treat a classified ad as proof of an independently verified business.
- Do not treat a marketplace product seller as a physical shop unless the source confirms that.
- Build a source registry so sources can be enabled/disabled without changing the main search orchestration code.

For the first working demo, prioritize Neshan and Balad. Then integrate Rasmio and the other sources as their actual capabilities allow.

## 5. MCP client implementation

Create a reusable MCP client/adapter layer.

Requirements:

- Launch each selected MCP package using its verified `uvx` command.
- Communicate using the MCP Python SDK and STDIO transport.
- Establish a session, initialize it, list available tools, and invoke only explicitly allowed tools.
- Validate tool arguments against the actual discovered schemas.
- Convert MCP results into a predictable internal representation without discarding the original response.
- Use bounded execution timeouts.
- Handle process startup errors, network errors, tool errors, malformed responses, and process termination.
- Close subprocesses and sessions reliably.
- Do not leave orphaned MCP processes.
- Do not start all MCP servers when a search only needs a subset.
- Do not run unbounded parallel requests.
- Implement per-source concurrency limits and retry policies.
- Do not retry indefinitely.
- Record each tool call, duration, result count, and error.

For the first MVP, it is acceptable to start an MCP subprocess for the duration of a search job and close it afterward. Keep the adapter interface flexible enough to support persistent MCP processes later.

Pin verified package versions. Do not blindly use unpinned latest versions in production.

## 6. Search orchestration

Implement deterministic search orchestration.

Input:
- Trade name
- Geographic scope
- Selected sources
- Optional maximum result count

The system should:

1. Normalize the Persian trade name and location.
2. Generate a limited set of deterministic search variants using a configurable dictionary of trade synonyms.
3. Select relevant sources based on the trade and geographic scope.
4. Execute the relevant MCP tools.
5. Follow pagination where the source supports it.
6. Fetch individual business details when the source provides a stable place/business identifier.
7. Preserve source-specific identifiers.
8. Save raw responses.
9. Normalize available fields.
10. Deduplicate records.
11. Produce a partial result if one or more sources fail.

Do not assume that repeating a search query or changing synonyms guarantees complete geographic coverage.

Do not claim that all businesses in a city or Iran have been discovered.

For a city-wide search, use the capabilities actually provided by each source. If geographic tiling or nearby searches are required, implement them only after verifying the source's actual tool schema and pagination/coverage limits.

Do not scrape or bypass login, CAPTCHA, access controls, or anti-bot restrictions.

## 7. Data model

Create suitable Django models. At minimum:

### SearchJob
- trade_name
- geographic_scope_type
- geographic_scope_name
- selected_sources
- status
- started_at
- completed_at
- total_raw_results
- total_unique_businesses
- total_errors
- error_summary

### SourceExecution
- search_job
- source_name
- status
- started_at
- completed_at
- request_count
- result_count
- error_count
- error_details

### BusinessLead
- search_job
- normalized_name
- original_name
- phone_numbers
- address
- city
- province
- website
- business_category
- latitude
- longitude
- source_names
- verification_status
- first_seen_at
- last_seen_at

### LeadEvidence
- business_lead
- source_name
- source_record_id
- source_url
- field_name
- field_value
- extraction_method
- collected_at
- raw_response

Use JSONField where appropriate, but keep important searchable fields as real database columns.

Never overwrite source evidence when a different source provides conflicting data.

Keep provenance at field level. A phone number from Neshan and a phone number from a company website must remain separately traceable.

Do not invent missing values.

## 8. Normalization and deduplication

Implement deterministic normalization:

- Persian and Arabic character normalization
- Normalize Persian/Arabic digits
- Normalize phone numbers without destroying the original value
- Normalize URLs and domains
- Normalize whitespace and punctuation
- Normalize city and province names

Deduplication should use a conservative matching strategy:

1. Same source + same source record ID.
2. Same normalized phone number, where appropriate.
3. Same normalized website/domain.
4. Name + address similarity as a candidate match, not an automatic merge when ambiguous.
5. Preserve branch-level businesses separately when they have distinct locations.

Do not merge two businesses solely because their names are similar.

Keep the evidence for every merged record.

## 9. Contact information quality

The purpose is to collect public business contact information.

Distinguish:
- Public business phone numbers
- Personal phone numbers belonging to private classified-ad sellers
- Unverified phone numbers
- Conflicting phone numbers

Do not turn private personal contact details from classified ads into advertising leads.

Implement deterministic phone validation for Iranian mobile and landline formats. Validation of format must not be described as proof that a phone number is active or belongs to that business.

Use explicit verification statuses, for example:
- discovered
- source_confirmed
- cross_source_confirmed
- invalid_format
- conflicting
- unverified

## 10. Django interface

Build a clean Persian RTL interface using Django Templates and local CSS.

Pages:

### Search form
- Trade name
- Scope: city / province / all Iran
- City/province field
- Source selection
- Maximum results
- Submit button

### Search job detail
- Job status
- Progress information
- Per-source status
- Result counts
- Error messages
- Total unique records
- Refresh/polling mechanism

### Results page
- Business name
- Phone
- Address
- City
- Website
- Source
- Verification status
- Link to source evidence

Add filtering by:
- Source
- City
- Has phone
- Has website
- Verification status

Add pagination.

### Downloads
- Excel (.xlsx)
- JSON (.json)

Excel should have a clean Persian header row and separate columns for phone, address, website, source, and verification status.

Include a second Excel sheet containing source evidence where practical.

JSON must be generated from the actual database records, not from an LLM.

## 11. Search job execution

Use Celery for long-running work.

Requirements:
- Search must not run inside a normal HTTP request.
- Return the job ID immediately.
- Update job and source statuses during execution.
- Support partial success.
- Use task time limits and source-specific timeouts.
- Handle worker restarts and failed tasks.
- Avoid duplicate execution of the same job.
- Keep a clear error log for each source.
- Make result exports available after completion or partial completion.

Use Redis as the Celery broker if available.

## 12. Security and operational requirements

- Keep secrets and proxy settings in environment variables.
- Never commit API keys or credentials.
- Protect search and export pages with Django authentication if the project already has authentication.
- Keep CSRF protection enabled.
- Validate all user input.
- Restrict export access to authorized users.
- Apply request and result limits.
- Sanitize filenames.
- Do not expose internal exception traces to the browser.
- Log useful technical details server-side.
- Make source connectors independently configurable.
- Respect the source websites' terms, data-use restrictions, and rate limits.
- Do not bypass access restrictions.

## 13. Deployment

Inspect the existing server deployment before changing anything.

Provide a deployment-ready setup for:
- Django / Gunicorn
- Celery worker
- Redis
- PostgreSQL if applicable
- Nginx if applicable

Create or update:
- requirements/dependency files
- environment example file
- systemd service files if the server uses systemd
- migration commands
- deployment instructions
- health-check instructions
- MCP installation/setup instructions

Do not overwrite existing production configuration without inspecting it first.

Do not restart or stop existing services without explaining the impact and obtaining approval.

## 14. Testing

Add tests for:

- MCP client connection and tool invocation using mocked MCP servers.
- Tool schema validation.
- Source failures and partial success.
- Persian text normalization.
- Phone normalization.
- Deduplication.
- Branch preservation.
- Conflicting source evidence.
- Search job status transitions.
- Excel export.
- JSON export.
- Authorization and export access.

Do not make the test suite depend on live Iranian websites.

Add a separate manual live-test command for checking actual MCP connectivity and tool responses.

## 15. Delivery requirements

Implement the working MVP, not just a design document.

At the end, provide:

1. Summary of implemented features.
2. Exact MCP packages installed and their pinned versions.
3. Actual tool names used by each connector.
4. Environment variables required.
5. Database migration commands.
6. Local run commands.
7. Server deployment commands.
8. How to perform a real test search, e.g. طلافروشی‌های اصفهان.
9. Known limitations and unverified source capabilities.
10. Any manual steps that still require my action.

Do not claim a source works unless it has been tested or clearly label it as unverified.

Prioritize a functioning, reliable Neshan + Balad search and the complete Django job/result/export workflow first. Add the remaining sources through the same architecture without breaking the working implementation.

The result should be a production-minded, deployable MVP with deterministic processing, source traceability, error handling, and a clean Persian interface.