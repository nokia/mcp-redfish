# Python runtime support

## Current policy

| Python version | Status |
| --- | --- |
| **3.14+** | Supported and recommended (containers, CI quality/e2e, local dev via `.python-version`) |
| **3.13** | Supported for now, **deprecated** — emits a `FutureWarning` and log warning at server startup |
| **< 3.13** | Not installable (`requires-python = ">=3.13"` in `pyproject.toml`) |

Python 3.13 remains installable while users migrate. A future release will raise
`requires-python` to `>=3.14` and remove the 3.13 CI matrix leg.

## User-visible deprecation

When the server starts on Python 3.13, `src.main` emits:

- a **`FutureWarning`** (visible in dev/test when warnings are enabled)
- a **WARNING** log line (visible with default `MCP_REDFISH_LOG_LEVEL=INFO`)

Python 3.14+ starts without this notice.

## Technical debt when dropping Python 3.13

When 3.13 support is removed, update all of the following in one change set:

### Packaging and metadata

- `pyproject.toml`: `requires-python = ">=3.14"`
- `README.md`, `AGENTS.md`, `.github/copilot-instructions.md`: remove 3.13 references
- Remove `_warn_deprecated_python_runtime()` from `src/main.py` and its test

### CI/CD

- `.github/workflows/ci-cd.yml`: drop `3.13` from the test matrix (keep `3.14` only)

### Tooling (Ruff exception)

Ruff is intentionally pinned below the production runtime today:

```toml
[tool.ruff]
target-version = "py313"  # NOT py314 while 3.13 is supported
```

**Why:** With `target-version = "py314"`, `ruff format` rewrites multi-exception
handlers to PEP 758 syntax (`except A, B:`), which is a **syntax error on Python
3.13**. Parenthesized `except (A, B):` remains valid on 3.14, so keeping Ruff on
`py313` is the correct dual-version workaround until 3.13 is dropped.

There is no formatter opt-out on `py314` yet; see
[astral-sh/ruff#25901](https://github.com/astral-sh/ruff/issues/25901).

**After dropping 3.13:**

1. Set `[tool.ruff] target-version = "py314"`.
2. Run `make format` to apply PEP 758 `except` style where desired.
3. Confirm `make ci-quality` passes.

MyPy `python_version = "3.14"` can stay as-is before and after the transition.

### Lockfile

- Run `uv lock` after changing `requires-python`.
- Verify `uv sync --locked` on Python 3.14 only.

## Verification checklist (post-3.13-removal)

```bash
uv sync --extra dev --extra test
make ci-all
```

Confirm no `FutureWarning` tests remain and the test matrix runs on 3.14 only.
