> Verified: 2026-11-23 · Source: [standards](https://github.com/clipvoz/standards) and the official docs of each tool.

# Git workflow

- One topic per commit, small enough to review. Conventional prefix (`feat:`, `fix:`, `test:`,
  `docs:`, `chore:`, `ci:`, `refactor:`) and a short imperative subject. The body explains **why**
  when it is not obvious.
- A feature and its tests go in the same commit, or the tests come immediately after.
  Never commit code that fails `ruff`, `mypy` or `pytest`.
- NEVER commit `.env`, keys, tokens or database dumps.
- Do not rewrite published history.
