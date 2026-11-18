# Architecture

The Python package separates recording, scheduling, persistence, replay, evaluation, scoring, and rendering. Framework dependencies are lazy and optional. Importing the core never opens the network.

`Recorder.call` / `acall` → budget admission → select one matching seeded fault → mutate request if applicable → pre-dispatch error/delay → invoke controlled function → mutate result/post-commit error → screen serialized inputs/results/errors → append event → explicit independent `finish` verdict → transactional store.

Events record dispatch order. Async tools may complete in another order; await all of them before finishing. Async cancellation is recorded and re-raised. The synchronous API cannot forcibly interrupt arbitrary blocking functions; set timeouts on the underlying client. `acall(timeout=...)` bounds the awaited coroutine, excluding injected pre-dispatch delay. A maximum call count and per-call cost reservation prevent admission beyond declared budgets.

SQLite connections are short-lived, explicitly closed, and transaction-scoped; WAL supports concurrent worker writes. JSONL is the portable contract; DuckDB is an optional export engine, not a server dependency. Parquet exports keep nested traces. Hosted Postgres/object-store persistence is not part of v0.1.

## Replay

`Replay` makes an isolated copy, enforces order/name/kind/sanitized arguments, and returns recorded sanitized outputs or recorded errors. It applies the recorded request drift to compare an original request. It never executes functions. Replay cannot reproduce the external side effect itself; use a controlled sandbox ledger for independent state assertions. Sensitive values redacted to the same marker are not distinguishable. Replay is a debugging tool, not cryptographic input attestation.

`Replay.verify()` validates the entire tape; it does not re-execute agent reasoning. `assert_consumed()` detects early termination. Re-running an agent against a tape can reveal changed control flow at the first divergence. A new model call requires a separate live experiment and can incur real costs.

## HTTP proxy

`pruefstand proxy --upstream http://127.0.0.1:11434/v1 --port 8787 --fault rate_limit` exposes a loopback-only, buffered JSON POST proxy. Route it to a **test** upstream. Credentials are read from `PRUEFSTAND_UPSTREAM_API_KEY` (or another named environment variable); caller cookies and authorization headers are not forwarded. Upstream redirects are refused. Bodies are bounded to 1 MiB. GET `/health` checks readiness. No CONNECT, arbitrary upstream selection, chunked requests, or streaming responses.

One request becomes one unlabelled trace. Set an independent verdict using `pruefstand label --db … RUN_ID --success true --harmful-actions 0 --loss-eur 0` before scoring. A suite of proxy requests does not automatically form an agent-level trace. Fault call numbers reset per incoming request; use the SDK for a multi-step schedule.

The proxy can inject a post-commit timeout, so never connect it to real payments or irreversible production operations. Its localhost binding is not authentication against other local processes. It is not a production gateway.

## Telemetry

`export_run(run, tracer)` emits parent/child spans through an application-configured OpenTelemetry tracer, with selected GenAI attributes, model usage, cost, and errors. The tracer/exporter and collector configuration belong to the caller. `otlp_json` is a diagnostic mapping, explicitly **not** an OTLP wire payload. No standalone OTLP collector is shipped.

## Docker execution

```bash
docker build -t pruefstand:local .
mkdir -p artifacts/container
docker run --rm --network none --read-only --cap-drop ALL \
  --security-opt no-new-privileges --pids-limit 128 --memory 512m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --mount type=bind,src="$PWD/artifacts/container",dst=/output \
  pruefstand:local run --out /output --repeats 5
```

The image runs as UID 10001; on Linux, make the output directory writable by that UID before launching. Docker execution is verified by the CI container job. The local worker pool runs trusted Python functions **in process**; threads are not a sandbox and cannot enforce process CPU/memory/wall-time limits. The container flags reduce privileges but are not a hardened isolation boundary for hostile code. Custom agent evaluation requires controlled credentials and tools.
