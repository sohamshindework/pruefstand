# Contributing

Use Python 3.11+ and Node 22.18+. Install `pip install -e '.[dev]'`, run `python -m pytest`, `node --test sdk/typescript/test/*.test.ts`, and `python -m build`. Optional framework checks use `pip install -e '.[frameworks]'`. Keep the core dependency-free and new fault delays bounded.

A good first contribution is a reproducible fault with a fixture, a regression test of the actual consequence, and a clear applicability/limitation note. For metric changes, change the metric version, explain the sampling unit, and never silently accept an updated CI baseline. Generated fixture results must stay labelled synthetic.

Do not commit secrets, personal traces, real customer data, unreviewed third-party ratings, or copied proprietary prompts. Open a narrowly scoped pull request describing the observed failure, the change, and verification. Security reports should follow SECURITY.md.
