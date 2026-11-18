# Intelligent Search Query Expansion — Implementation Instructions

## 1. Objective

Improve business discovery completeness by intelligently expanding the user's original search terms before executing searches across available sources.

When a user submits a search keyword, the system should identify relevant alternative search terms, including:

- Synonyms and near-synonyms.
- Related industry and business terminology.
- Alternative names commonly used in the Iranian market.
- Singular and plural variations.
- Common Persian spelling variations.
- Colloquial and formal expressions.
- Common abbreviations and alternative expressions.
- Relevant product, service, and business-category terminology.
- English equivalents and Persian transliterations when useful.
- Commonly used commercial names for the same business category.

The goal is to discover relevant businesses that would otherwise be missed by searching only the original keyword.

This feature must integrate with the existing multi-source search architecture without breaking source compatibility, increasing irrelevant results, or unnecessarily consuming MCP request quotas.

## 2. LLM-Based Query Expansion

Investigate and implement an intelligent query expansion component.

The component should:

1. Receive the original user search query.
2. Understand its semantic meaning and search intent.
3. Generate a controlled set of relevant alternative search terms.
4. Remove duplicates and semantically irrelevant terms.
5. Preserve the original query.
6. Rank alternative queries by relevance and expected search usefulness.
7. Return structured, validated output to the application.

An LLM may be used for semantic expansion.

However:

- Do not make the entire search pipeline dependent on the LLM.
- Support configurable LLM providers and models.
- Reuse existing LLM infrastructure if available.
- Cache expansion results to avoid repeatedly spending tokens on identical queries.
- Use deterministic local normalization and predefined synonym dictionaries as fallback.
- If the LLM is unavailable, slow, or returns invalid output, continue searching with the original query.
- Do not allow LLM failures to fail the entire SearchJob.

The expansion process must have configurable limits, including:

- Maximum generated query variants.
- Maximum LLM retries.
- LLM timeout.
- Cache expiration.
- Maximum tokens or cost per expansion.

## 3. Source-Specific Query Compatibility — CRITICAL

This is the most important requirement.

Different MCP sources have different search capabilities, tool schemas, accepted parameters, and search semantics.

The system MUST NOT assume that every source supports the same query format or the same search behavior.

For example:

- A source may accept a single free-text `query`.
- Another source may support structured category and location parameters.
- Another may search only predefined business categories.
- Another may search product names rather than business categories.
- Some sources may have their own search operators or restrictions.
- Some sources may not support multiple keywords or query variants at all.

Before sending an expanded query to a source, inspect that source's actual adapter implementation, MCP tool schema, parameter definitions, and documented capabilities.

Implement a source-aware query adaptation layer.

For every source:

1. Identify the actual search tool and its supported parameters.
2. Determine whether it supports free-text search, categories, multiple keywords, or other query structures.
3. Determine whether query expansion is useful and compatible with that source.
4. Convert generated variants into the format accepted by that source.
5. Reject unsupported query formats before calling the MCP tool.
6. Never invent parameters or assume undocumented functionality.
7. Never send a list or structured object to a parameter that only accepts a string.
8. Never modify an MCP tool's required arguments in a way that violates its schema.

If a source supports only one search query per request, execute compatible variants as separate searches when the available request budget permits.

If a source does not support expanded queries, use its original supported search mechanism without expansion.

Each adapter must explicitly declare or implement its query capabilities. Avoid a generic implementation that blindly sends all variants to all sources.

## 4. Search Strategy and Query Prioritization

Do not execute every generated keyword against every source without considering relevance, cost, and available quotas.

Implement a controlled query execution strategy.

Suggested priority:

1. Original user query.
2. Highly relevant synonyms.
3. Common alternative names.
4. Relevant industry-specific terms.
5. Relevant product or service terminology.
6. Less common spelling and language variations.

The original query must always receive priority.

Query variants should be executed according to:

- Source compatibility.
- Search relevance.
- Remaining source request budget.
- Remaining global MCP request budget.
- Existing results.
- Previous query execution history.
- Source performance and rate-limit status.

Avoid spending requests on variants that are unlikely to produce new businesses.

The system should stop executing redundant variants when they consistently produce no new unique businesses.

However, do not prematurely stop useful searches merely because one variant returns few results.

## 5. Persian Language and Iranian Market Considerations

Pay special attention to Persian-language search behavior.

Examples of useful normalization and expansion:

- آرایشگاه، سالن زیبایی، پیرایشگاه، مرکز زیبایی
- تعمیرگاه خودرو، مکانیکی، اتوسرویس، خدمات خودرو
- فروشگاه موبایل، موبایل فروشی، فروشگاه تلفن همراه
- کافه، کافی‌شاپ، قهوه‌فروشی
- شیرینی‌فروشی، قنادی، فروشگاه شیرینی
- تجهیزات پزشکی، فروشگاه لوازم پزشکی، کالای پزشکی

These examples are illustrative, not a fixed dictionary.

The system should distinguish between:

- True synonyms.
- Closely related business categories.
- Products and services associated with a business.
- Merely associated words that may cause irrelevant results.

Do not treat every semantically related term as an interchangeable synonym.

For example, a query for a car repair shop should not automatically expand into car dealerships, car rental agencies, or car parts manufacturers unless the user's intent supports those categories.

Persian normalization should account for:

- ی and ي.
- ک and ك.
- Half-spaces and whitespace.
- Common spelling differences.
- Arabic/Persian character variants.
- Common colloquial spellings.

Normalization must not destroy meaningful distinctions between different business names or categories.

## 6. Structured Expansion Output

Use a structured internal representation for generated queries.

A possible conceptual structure:

```json
{
  "original_query": "تعمیرگاه خودرو",
  "variants": [
    {
      "query": "مکانیکی خودرو",
      "type": "synonym",
      "relevance": 0.95
    },
    {
      "query": "اتوسرویس",
      "type": "related_term",
      "relevance": 0.85
    }
  ]
}
```

This is an internal application structure, not an instruction to require the LLM to generate arbitrary MCP arguments.

The LLM should generate search terminology only.

The application must remain responsible for:

- Validating generated output.
- Selecting source-compatible variants.
- Constructing MCP arguments.
- Enforcing quotas.
- Executing searches.
- Deduplicating results.
- Persisting execution history.

Never let the LLM directly control MCP tool arguments or bypass adapter validation.

## 7. Deduplication and Search History

Expanded searches will naturally produce overlapping results.

Ensure that:

- The same query variant is not unnecessarily executed repeatedly.
- Normalized duplicate variants are removed.
- Businesses returned by multiple variants are deduplicated using the existing business matching logic.
- Existing LeadEvidence records are preserved and updated correctly.
- Each result retains its source and query provenance.
- The system can identify which original query and expanded variant discovered a business.

Do not discard useful evidence simply because a business was already discovered.

## 8. Integration with Existing Search Quotas

This feature must integrate with the existing dynamic source quota allocation and request-budget architecture.

Important requirements:

- Query expansion must not bypass global MCP call limits.
- Query expansion must not bypass per-source call limits.
- LLM requests and MCP requests must be accounted for separately.
- The original query must not be starved by generated variants.
- Sources with limited search capacity must not be overwhelmed.
- Expansion must respect source cooldowns and rate limits.
- Query execution must be resumable when a SearchJob is interrupted.

Expanded queries should participate in the existing dynamic allocation strategy rather than introducing a competing quota system.

## 9. Configuration and Observability

Provide configurable settings for:

- Enabling/disabling query expansion.
- Selected LLM provider and model.
- Maximum number of variants.
- Minimum relevance threshold.
- Maximum expansion cost.
- Cache expiration.
- Maximum variants executed per source.
- Query execution priority.

Record useful information for each SearchJob:

- Original query.
- Generated variants.
- Expansion provider/model.
- Expansion success or failure.
- Variants accepted and rejected.
- Rejection reasons.
- Variants executed by each source.
- Number of requests consumed.
- Unique businesses discovered per variant.

Expose useful information in the existing UI where appropriate, without overwhelming the user with technical details.

## 10. Testing Requirements

Add tests covering:

1. Correct synonym and alternative-term generation.
2. Persian normalization.
3. Duplicate variant removal.
4. Irrelevant variant rejection.
5. Invalid LLM responses.
6. LLM timeout and provider failure.
7. Fallback to the original query.
8. Source-specific query compatibility.
9. Sources that accept only one free-text query.
10. Sources that do not support query expansion.
11. MCP schema validation.
12. Request-budget enforcement.
13. Rate-limit and cooldown handling.
14. Deduplication across different query variants.
15. SearchJob cancellation and resumption.
16. Caching of expansion results.

Use mocked LLM responses and mocked MCP tools for deterministic tests.

Do not require live external services for the normal test suite.

## 11. Implementation Approach

Before changing code:

1. Inspect the existing search pipeline.
2. Inspect every source adapter and its actual MCP tool schema.
3. Identify the best integration point for query expansion.
4. Identify existing normalization, caching, quota, and deduplication mechanisms.
5. Document which sources can support which types of expanded queries.
6. Identify any sources where expansion should be disabled.

Then implement the feature using the existing project architecture.

Avoid unnecessary rewrites or introducing a second search orchestration system.

Keep the expansion component independent of individual MCP providers.

Each source adapter should remain responsible for translating compatible search terminology into its own supported request format.

## 12. Final Acceptance Criteria

The implementation is successful only if:

- A single user query can discover relevant businesses through multiple useful search expressions.
- The original query is always preserved and prioritized.
- Expanded terms are semantically relevant rather than arbitrary related words.
- Every source receives only queries compatible with its actual capabilities.
- No unsupported MCP arguments are introduced.
- Existing source integrations continue to work.
- Query expansion does not bypass request quotas or rate limits.
- Duplicate businesses are not unnecessarily stored.
- Search provenance remains available.
- The system continues working if the LLM is unavailable.
- Existing dynamic quota redistribution and resumable job execution remain functional.

**Important:** The purpose is not simply to generate more keywords. The purpose is to increase the number of relevant, unique businesses discovered while respecting the real capabilities and limitations of every individual search source.