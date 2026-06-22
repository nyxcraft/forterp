# Git hooks

Tracked hooks for this repo. Enable them once per clone:

```sh
git config core.hooksPath .githooks
```

## `pre-commit`

Two jobs, both keeping the tree in the state CI expects:

1. **Python format + lint.** Runs `ruff format` and `ruff check --fix` on the staged
   `.py` files, re-stages them, and aborts the commit if any unfixable lint remains — so
   formatting/import-order/`# noqa` hygiene is maintained at commit time, not just gated in
   CI. Needs `ruff` (`pip install -e ".[dev]"`); if it's absent the step is skipped with a
   warning (CI still gates it).
2. **Docs site sync.** Rebuilds the docs site and re-stages `gh-pages/public/` whenever a
   commit touches a site source (`docs/`, `CHANGELOG.md`, or anything under `gh-pages/`
   except the built output). Needs the docs extra (`pip install -e ".[docs]"`, for
   `markdown-it-py`); if absent the rebuild is skipped with a warning, and the CI "site
   freshness" check is the backstop.

Both re-stage whole files, so a partially-staged file will be committed in full.
