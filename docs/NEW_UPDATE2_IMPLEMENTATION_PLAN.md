# Implementation plan: MCP diagnostic and version consistency

## Audit status

- [x] Read `docs/new_update2.md` in full and inspect current adapters, MCP registry, source execution, health command, tests and dependency manifests.
- [x] Compare the supplied deployed schemas: `tb_find_shops` requires `query`; `job_companies` accepts nullable `name`, `site`, and `page` (no `query` property).
- [x] Check local package versions and repo pins. At audit start, the virtualenv held older releases, requirements were unconstrained, and the registry strings were stale.

## Work checklist

- [x] Fix `check_mcp` to use source-specific search arguments and avoid assuming every source has a detail tool.
- [x] Reuse adapters/schema-aware argument mapping wherever possible; preserve geographic probing for Neshan/Balad.
- [x] Make `--source all` report each failure and continue through the remaining sources, while returning a failing command status if any source failed.
- [x] Add regression tests for source schemas, optional details, valid details, truthful output/errors, and continuation after one failure.
- [x] Reconcile dependency and registry versions against the versions actually reported on the server and published package metadata.
- [x] Run focused and full project validation, then record exact server verification commands and deployment-only unknowns.

## Evidence / limitations

- `.venv` now uses torob-mcp 0.2.2, iran-jobs-mcp 0.2.1, digikala-mcp 0.6.2, and snappshop-mcp 0.2.1; `requirements.txt` and registry metadata match. Package dependencies resolved with no broken requirements.
- `check_mcp --schema-only` passed against all four updated local MCP processes. Torob and Iran Jobs schemas match the user's supplied production output exactly; Digikala and SnappShop expose the expected search/detail tool names and argument contracts.
- The four chosen releases are published as `PolyForm-Noncommercial-1.0.0`; package publishers state prior releases remain MIT and commercial/company/client-project use of the new releases requires a commercial license. This is called out in README and source audit.
- Offline tests use mock provider results. No live Torob/Iran Jobs provider search was sent; the actual `results=0` versus nonzero behavior still needs a bounded post-deploy search in the production network.
- Keep the user's pre-existing `leads/sources.py` modification intact unless an observed defect requires a narrowly scoped edit.

## Validation and operator commands

- `.venv\\Scripts\\python.exe manage.py test leads --verbosity 1`: ۵۸ تست اجرا شد و همگی موفق شدند.
- `.venv\\Scripts\\python.exe manage.py check`: clean.
- `.venv\\Scripts\\python.exe manage.py makemigrations --check --dry-run`: no pending migration.
- `.venv\\Scripts\\python.exe -m pip check`: no broken requirements.
- On Chabokan, after deploying code/dependencies, first run `python manage.py check_mcp --source torob --schema-only` and `python manage.py check_mcp --source iran_jobs --schema-only`; then run `python manage.py check_mcp --source torob --query "فروشگاه موبایل" --city "تهران"` and `python manage.py check_mcp --source iran_jobs --query "شرکت نرم افزاری" --city "تهران"`. The last two commands call provider websites; schema-only does not.
