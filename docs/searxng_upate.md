# Task: Integrate SearXNG into info_extractor

You are working on my existing GitHub project:

https://github.com/ARVIN-B/info_extractor

Your task is to inspect the entire existing codebase, understand its architecture, and properly integrate my self-hosted SearXNG search engine as a search provider.

**Important:** Do not start implementing anything before understanding the existing architecture, providers, MCP integrations, data collection pipeline, normalization, deduplication, and output formats.

## 1. SearXNG Server Configuration

I have an existing, operational SearXNG instance with the following configuration:

- Base URL: `https://195.248.240.152:8888`
- Search endpoint: `https://195.248.240.152:8888/search`
- Authentication: HTTP Header
- Authentication header name: `X-API-Key`
- API key environment variable: `SEARXNG_API_KEY`
- API response format: JSON

The API key is already stored in the project's `.env` file:

`SEARXNG_API_KEY=...`

Do not hardcode the API key or expose it in logs, reports, exceptions, or output files.

### Example API Request

```python
import os
import requests

url = "https://195.248.240.152:8888/search"

headers = {
    "X-API-Key": os.getenv("SEARXNG_API_KEY")
}

params = {
    "q": "شرکت های نرم افزاری ایران",
    "format": "json",
    "language": "fa",
    "pageno": 1
}

response = requests.get(
    url,
    headers=headers,
    params=params,
    timeout=30
)

response.raise_for_status()
data = response.json()
```

### Important Network Considerations

The server uses HTTPS with a self-signed IP certificate.

Investigate the correct TLS verification approach and implement it safely.

- Do not globally disable SSL verification.
- Do not automatically use `verify=False` without investigating the certificate.
- Prefer configuring a trusted CA certificate if available.
- If the certificate cannot be validated in the current environment, make the TLS configuration explicit and configurable.

HTTP requests are not supported. Always use HTTPS.

Requests without the `X-API-Key` header are rejected.

## 2. Initial Codebase Investigation

Before implementation:

1. Inspect the complete repository structure.
2. Identify the current search providers and their interfaces.
3. Inspect existing MCP integrations.
4. Understand how search queries are generated.
5. Understand how search results are collected and normalized.
6. Understand how URLs and root domains are deduplicated.
7. Understand how business information and phone numbers are extracted.
8. Inspect existing retry, timeout, pagination, rate-limit, and error-handling mechanisms.
9. Inspect existing configuration and `.env` loading.
10. Review existing tests and documentation.

Identify the best integration point for SearXNG.

Do not duplicate existing functionality or introduce unnecessary architectural changes.

## 3. SearXNG Provider Implementation

Implement SearXNG as a proper search provider following the existing project architecture.

Requirements:

- Use the existing HTTP client conventions where possible.
- Read credentials from environment variables.
- Support Persian and English queries.
- Support configurable search language.
- Support pagination using `pageno`.
- Support configurable request timeout.
- Support retry for transient network errors.
- Handle HTTP 400, 403, 429, 500 and other errors appropriately.
- Handle malformed JSON and unexpected response structures.
- Handle empty search results.
- Avoid duplicate requests where the existing architecture supports caching.
- Respect the existing provider abstraction and result schema.

Do not create a separate, disconnected search pipeline.

## 4. Search Result Processing

SearXNG results should enter the existing normalization and extraction pipeline.

Preserve useful information returned by SearXNG, including:

- title
- url
- content/snippet
- engine information, if available
- published date, if available
- other useful metadata

Do not discard potentially useful search metadata prematurely.

Normalize results into the project's existing internal schema.

Deduplicate results based on normalized URLs and root domains, following the existing project's rules.

Be careful not to incorrectly merge different business websites or discard useful subdomains.

## 5. Integration with Business Information Extraction

The primary objective of info_extractor is collecting business information, particularly:

- Business/company name
- Website
- Phone numbers
- Address
- Other available business metadata

SearXNG should improve the discovery stage.

It should help discover:

- Iranian company websites
- Business directories
- Company profile pages
- Contact pages
- About pages
- Business listing pages
- Relevant pages containing telephone numbers

Search results should not automatically be treated as verified business information.

Preserve source URLs and source attribution for extracted information.

Do not invent phone numbers, addresses, or company details.

Keep the distinction between discovered information and verified information.

## 6. Query Strategy

Inspect the existing query-generation mechanism.

Integrate SearXNG into the current strategy rather than creating an unrelated query generator.

Support:

- Persian queries
- English queries
- Industry-specific queries
- City-specific queries
- Company-name searches
- Phone-number discovery queries
- Website/contact-page discovery

Avoid sending identical queries repeatedly.

Make pagination configurable.

Do not assume that a single SearXNG query can return hundreds of results. Implement pagination and collect results incrementally.

## 7. Configuration

Add appropriate configuration variables to the existing configuration system.

At minimum, support:

```env
SEARXNG_API_KEY=
SEARXNG_BASE_URL=https://195.248.240.152:8888
SEARXNG_TIMEOUT=30
SEARXNG_LANGUAGE=fa
SEARXNG_ENABLED=true
SEARXNG_MAX_PAGES=5
```

The existing `.env` variable `SEARXNG_API_KEY` must be reused.

Do not overwrite existing environment variables or break existing configurations.

Keep reasonable defaults and follow existing project conventions.

## 8. Testing

Implement tests for:

1. Successful SearXNG connection.
2. API key authentication.
3. Missing API key.
4. Invalid API key.
5. Successful JSON response parsing.
6. Empty results.
7. Pagination.
8. Timeout.
9. Network failures.
10. HTTP 429 handling.
11. Malformed JSON.
12. URL normalization and deduplication.
13. Integration with the existing extraction pipeline.

Use mocked HTTP responses for unit tests.

Also provide a real integration test that can be run manually against my SearXNG server.

Never expose the API key in test output.

## 9. Documentation

Update the project's documentation.

Explain:

- How SearXNG is configured.
- Required environment variables.
- How authentication works.
- How to enable or disable the provider.
- How to run the connection test.
- How pagination works.
- How SearXNG integrates with other providers.
- Known limitations and troubleshooting.

## 10. Implementation Constraints

These requirements are important:

- Preserve the existing project architecture.
- Do not remove existing MCP integrations.
- Do not break existing search providers.
- Do not replace existing extraction logic unnecessarily.
- Do not introduce hardcoded API keys.
- Do not expose credentials in logs.
- Do not fabricate search results.
- Do not silently ignore provider errors.
- Avoid unnecessary dependencies.
- Avoid unnecessary refactoring.
- Keep the implementation modular and maintainable.

## 11. Final Deliverables

After implementation:

1. Provide a summary of the existing architecture you discovered.
2. Explain where SearXNG was integrated.
3. List all modified and newly created files.
4. Explain the request and response flow.
5. Explain how to run the integration test.
6. Report the actual connection test result if you were able to execute it.
7. Report any remaining issues or limitations.

**Execution instruction:**

Do not stop after writing a proposed implementation plan. Inspect the repository, implement the integration, run the relevant tests, fix any regressions, and update the documentation.

Work incrementally and preserve all existing functionality.