# Git hooks

Tracked hooks for this repo. Enable them once per clone:

```sh
git config core.hooksPath .githooks
```

## `pre-commit`

Rebuilds the docs site and re-stages `gh-pages/public/` whenever a commit touches a site
source (`docs/`, `CHANGELOG.md`, or anything under `gh-pages/` except the built output).
This keeps the committed site in sync with its source automatically.

Requires the docs extra (`pip install -e ".[docs]"`, which pulls in `markdown-it-py`). If
it's missing the hook skips the rebuild with a warning rather than blocking the commit; the
CI "site freshness" check is the backstop that catches a stale committed site.
