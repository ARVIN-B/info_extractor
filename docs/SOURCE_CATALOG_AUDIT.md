# Source catalog audit

Audit date: 2026-11-16. The catalog below is based on the requested `sepehr071/iran-mcp` server catalog and each installed MCP's live `list_tools()` output. A schema check confirms the stdio server and its tool contract; it does not prove that a source website is reachable from the production network or that every query returns records.

## Integrated

| Source | Use in this app | Evidence / boundaries |
|---|---|---|
| Neshan, Balad | Local places and business contacts | Existing adapters kept; persistent provider cooldown and a local-business fallback group. |
| Emalls | Product listings to shop profiles | Existing adapter kept; online-shop fallback group. |
| Basalam | Marketplace vendors | Existing adapter kept; a vendor listing is not treated as an independent contact unless the source reports it. |
| Rasmio | Registered-company discovery | Existing public company search kept; no repeated guest profile opens. |
| Torob 0.2.1 | Direct shop-name/domain discovery with `tb_find_shops` | Installed in `.venv`; live schema checked. Catalog marks it unofficial/read-only; the source says cloud/foreign egress may be blocked. Repository metadata declares MIT. |
| Iran Jobs 0.2.0 | Employer company discovery across IranTalent, Jobinja, Jobvision via `job_companies` | Installed in `.venv`; schema checked. Company results are Leads; individual job ads are not. MIT per package metadata. |
| Quera 0.2.0 | Quera Magnet employer search and company profile via `qr_companies` / `qr_company` | Installed in `.venv`; live schema checked. Profile exposes public company address, website and social links when present; tech-company coverage only. MIT per package metadata. |
| Digikala 0.6.1 | Product search then seller offers from `dk_product` | Installed in `.venv`; schema checked. Seller ID/name are retained; Digikala profile links are provenance, not the seller's official website. MIT per package metadata. |
| SnappShop 0.2.0 | Product search then seller offers from `ss_product` | Installed in `.venv`; schema checked. Product ID is distinct from the product's short review ID; seller offers do not guarantee contact details. Source project says Iranian egress is required. MIT per package metadata. |

## Reviewed, not integrated

| Source family | Decision |
|---|---|
| Ponisha and Karlancer | Public project/freelancer profiles are available in the catalog, but a project client is not necessarily a company and freelancer records are people. Do not turn them into business Leads without a separate verified organization identity and suitable public-business-only policy. |
| Divar and Sheypoor | Classified advertisements mix businesses with personal listings, residences, and individual contact data. No generic classifieds ingestion was added to this business-contact application. A future integration needs business-category filtering, source rules review, and a public-business-only extraction contract. |
| e-Estekhdam | No reviewed MCP entry with a verifiable tool schema was found in the requested catalog. No undocumented endpoint or page scraper was assumed. |
| Additional marketplace/product servers (for example Technolife and fashion/appliance catalogs) | They could increase retail coverage, but the first release prioritizes the four requested shop sources plus Quera, which exposes employer profiles rather than product-only cards. Add another connector only after checking its exact schema and distinct coverage. |

All installed MCPs remain opt-in according to `ENABLED_MCP_SOURCES`. The repository's existing `.env` was not changed. New source packages and commands are pinned in `requirements.txt`; install/update using the project interpreter only.
