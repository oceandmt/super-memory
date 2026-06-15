# Contributing to Super Memory

Thanks for helping improve Super Memory.

## Development setup

```bash
git clone <repo-url>
cd super-memory
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
pytest
```

## Contribution guidelines

- Keep workspace Markdown as the canonical local memory layer.
- Do not commit real memory databases, credentials, tokens, or machine-specific paths.
- Add tests for new CLI, MCP, adapter, and guardrail behavior.
- Prefer deterministic behavior for baseline memory operations.
- Document public-facing behavior in `README.md` or `docs/`.

## Pull request checklist

Before opening a PR:

- [ ] Tests pass with `pytest`
- [ ] No secrets or private paths are committed
- [ ] Docs are updated when behavior changes
- [ ] New public APIs include basic usage examples
- [ ] Backward compatibility or migration notes are included when relevant

## Security issues

Please do not open public issues for vulnerabilities or credential exposure. Use the security reporting instructions in `SECURITY.md` if available, or contact the maintainers privately.
