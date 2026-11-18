# Release validation — 18 November 2026

Local release checks passed on Python 3.14.2 and Node 25.2.1:

- 66 Python tests, including real LangGraph/OpenAI Agents/MCP contracts and loopback HTTP proxy integration tests.
- Three Node/TypeScript SDK tests.
- 89% Python statement coverage (rounded).
- Wheel and source distribution build; a clean virtual environment installed the wheel with no dependencies and completed the demo.
- Full synthetic experiment: 1,680 runs over eight workflows and 21 conditions for two agents.
- The vulnerable retry fixture: 47.6% task success, 80 harmful runs. The idempotent fixture: 100% task success, zero observed harmful runs.
- A real LangGraph graph re-executed against recorded tools 10/10 times with identical output and no additional ledger actions.
- Browser checks: published dashboard, trace inspection/filtering, fault-category filtering, impact calculator, and the recorded before/after demo.

GitHub CI also passed Python 3.11, 3.12, 3.13, and 3.14 jobs, the optional framework contract job, Node checks, the reliability gate, and a non-root Docker execution with networking disabled. See the repository’s Actions history for commit-specific results. The GitHub Pages dashboard deployment succeeded.

Optional integrations tested locally: LangGraph 1.2.22, OpenAI Agents 0.25.0, MCP 2.3.0, HTTPX 0.28.1, DuckDB 2.0.0, and OpenTelemetry SDK 1.45.2. Framework dependencies emit upstream deprecation warnings on Python 3.14; no test failures resulted.

These checks establish behavior for the covered code and synthetic fixtures. They do not establish reliability of external agents or live LLMs, GDPR/AI Act compliance, production performance, or effectiveness of a hardened hostile-code sandbox. The roadmap separates those remaining experiments from shipped software.
