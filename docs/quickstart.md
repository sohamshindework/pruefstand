# Quickstart

Python 3.11+, with `pip install -e .` from the checkout. No API key is needed for the fixtures.

```bash
pruefstand demo --out artifacts/demo
pruefstand run --out artifacts/run --repeats 5 --workers 4 --seed 42
pruefstand list --db artifacts/run/traces.db --agent vulnerable-retry
```

Copy a run ID from `list`:

```bash
pruefstand show --db artifacts/run/traces.db RUN_ID
pruefstand replay --db artifacts/run/traces.db RUN_ID --times 10
```

The CLI replay command validates the recorded tape ten times. To rerun your agent’s control flow, create `Replay(run)` and replace every tool/model call with `replay.call(name, arguments, kind=...)`; then call `assert_consumed()`. Replay never executes real tools. It returns sanitized recorded values, which can change an agent that depends on exact sensitive strings. See [integration details](integrations.md).

Every suite writes:

```text
artifacts/run/
  traces.db               SQLite WAL trace store
  traces.jsonl            Portable, one run per line
  profiles.json           All agent profiles
  profiles/*.json         Individual profiles for CI
  roi/*.json              Explicit euro-impact scenarios
  report.html             Standalone report
  evidence.zip            Evidence files and integrity manifest
```

Other commands:

```bash
pruefstand faults
pruefstand run --agent idempotent-agent --fault timeout_after --fault prompt_injection
pruefstand score --db artifacts/run/traces.db --agent idempotent-agent --out artifacts/profile.json
pruefstand export --db artifacts/run/traces.db --out artifacts/runs.parquet --format parquet
pruefstand import artifacts/run/traces.jsonl --db artifacts/imported.db
pruefstand evidence --db artifacts/run/traces.db --out artifacts/evidence.zip
pruefstand roi --profile artifacts/run/profiles/vulnerable-retry.json --monthly-runs 50000
pruefstand site-data --db artifacts/run/traces.db --out ratings/dist/data.json
```

Parquet export needs `pip install -e '.[analytics]'`. A clean output directory gives an unambiguous experiment. Repeating exactly the same task/agent/condition/seed replaces the same deterministic run ID; changing repetition counts leaves older rows in an existing database. Use a new `--out` for changed protocols. Reports for a suite use the current run set; store-wide exports include the entire store.

Budget admission checks `--max-calls` per run and partitions `--budget-eur` evenly across all jobs. A recorded model call must declare its maximum possible charge through `max_cost_eur` for meaningful cost bounds. This is a conservative reservation charged even on errors, not a provider invoice. Tokens are populated by the model adapter. Duration is the sum of intercepted calls, not wall-clock duration for concurrent runs.

Exit codes: `0` success, `1` failed CI gate, `2` invalid arguments/data or a handled operational error. Agent failures are experiment observations and do not make the suite command fail; apply the gate to enforce a policy.
