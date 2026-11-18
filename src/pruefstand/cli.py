"""The command line interface; real work is exposed through the Python API too."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .faults import CATALOG, ChaosPlan, Fault
from .replay import Replay
from .reports import evidence_pack, html_report, roi, write_json
from .runner import SuiteConfig, run_demo, run_suite
from .schema import Run, utcnow
from .scoring import compare_markdown, gate, profile
from .store import Store


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def profiles_for(runs, iterations=1000):
    return [profile([r for r in runs if r.agent == agent], iterations=iterations) for agent in sorted({r.agent for r in runs})]


def bundle(runs, output: Path, store: Store, iterations=1000):
    profiles = profiles_for(runs, iterations)
    for p in profiles:
        # User-supplied entrypoint names can contain path separators; use a stable safe slug.
        from .schema import fingerprint
        name = p["agent"] if p["agent"].replace("-", "").replace("_", "").isalnum() else fingerprint(p["agent"])[:16]
        write_json(output / "profiles" / f"{name}.json", p)
        write_json(output / "roi" / f"{name}.json", roi(p))
    write_json(output / "profiles.json", profiles)
    html_report(profiles, runs, output / "report.html")
    store.export_jsonl(output / "traces.jsonl")
    evidence_pack(runs, profiles, output / "evidence.zip")
    return profiles


def make_parser():
    parser = argparse.ArgumentParser(prog="pruefstand", description="Crash-test AI agents. Record • replay • inject • measure.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("demo", "run"):
        command = commands.add_parser(name, help="Run the synthetic refund demo" if name == "demo" else "Run an enterprise reliability suite")
        command.add_argument("--out", type=Path, default=Path("artifacts") / name)
        command.add_argument("--repeats", type=int, default=5)
        command.add_argument("--seed", type=int, default=42)
        command.add_argument("--bootstrap", type=int, default=1000)
        if name == "run":
            command.add_argument("--agent", action="append", help="Builtin or trusted Python module:callable; repeat to compare")
            command.add_argument("--tasks", type=Path, help="Task JSON pack with a tasks array")
            faults = command.add_mutually_exclusive_group()
            faults.add_argument("--fault", action="append", choices=sorted(CATALOG))
            faults.add_argument("--no-chaos", action="store_true")
            command.add_argument("--workers", type=int, default=4)
            command.add_argument("--budget-eur", type=float, default=5)
            command.add_argument("--max-calls", type=int, default=30)
    for name in ("score", "report", "evidence", "export", "list", "show", "replay", "label", "site-data"):
        command = commands.add_parser(name)
        command.add_argument("--db", type=Path, default=Path("artifacts/run/traces.db"))
        if name in {"score", "report", "evidence", "export", "site-data"}:
            command.add_argument("--out", type=Path, required=True)
        if name in {"score", "report", "evidence", "site-data"}:
            command.add_argument("--bootstrap", type=int, default=1000)
        if name in {"list", "score"}:
            command.add_argument("--agent")
        if name in {"show", "replay", "label"}:
            command.add_argument("run_id")
        if name == "replay":
            command.add_argument("--times", type=int, default=10)
        if name == "label":
            command.add_argument("--success", choices=["true", "false"], required=True)
            command.add_argument("--confidence", type=float)
            command.add_argument("--harmful-actions", type=int, required=True)
            command.add_argument("--loss-eur", type=float, required=True)
        if name == "export":
            command.add_argument("--format", choices=["jsonl", "parquet"], default="jsonl")
    command = commands.add_parser("import")
    command.add_argument("source", type=Path)
    command.add_argument("--db", type=Path, required=True)
    command = commands.add_parser("gate")
    command.add_argument("--baseline", type=Path, required=True)
    command.add_argument("--candidate", type=Path, required=True)
    command.add_argument("--max-drop", type=float, default=.05)
    command.add_argument("--min-runs", type=int, default=20)
    command.add_argument("--min-tasks", type=int, default=3)
    command.add_argument("--minimums", type=Path)
    command.add_argument("--out", type=Path)
    command.add_argument("--markdown", type=Path)
    command = commands.add_parser("roi")
    command.add_argument("--profile", type=Path, required=True)
    command.add_argument("--monthly-runs", type=int, default=50_000)
    command.add_argument("--review-cost-eur", type=float, default=2)
    command.add_argument("--max-monthly-loss-eur", type=float, default=1000)
    command.add_argument("--out", type=Path)
    command = commands.add_parser("faults")
    command.add_argument("--json", action="store_true")
    command = commands.add_parser("proxy")
    command.add_argument("--upstream", required=True)
    command.add_argument("--port", type=int, default=8787)
    command.add_argument("--db", type=Path, default=Path("artifacts/proxy/traces.db"))
    command.add_argument("--fault", choices=sorted(CATALOG))
    command.add_argument("--seed", type=int, default=42)
    command.add_argument("--api-key-env", default="PRUEFSTAND_UPSTREAM_API_KEY")
    return parser


def dispatch(args):
    command = args.command
    if command in {"demo", "run"}:
        store = Store(args.out / "traces.db")
        if command == "demo":
            runs = run_demo(store, args.repeats, args.seed)
        else:
            runs = run_suite(agents=args.agent, tasks=read_json(args.tasks)["tasks"] if args.tasks else None,
                             faults=[] if args.no_chaos else args.fault,
                             config=SuiteConfig(args.repeats, args.seed, args.workers, args.budget_eur, args.max_calls), store=store)
        profiles = bundle(runs, args.out, store, args.bootstrap)
        for p in profiles:
            print(f"{p['agent']}: {p['n_runs']} runs; success {p['metrics']['success_rate']['value']:.1%}; harmful runs {p['harmful_runs']}")
        print(f"Report: {(args.out / 'report.html').resolve()}")
        print("Synthetic fixture results are demonstrations, not third-party framework ratings.")
        return 0
    if command == "gate":
        result = gate(read_json(args.baseline), read_json(args.candidate), max_drop=args.max_drop,
                      min_runs=args.min_runs, min_tasks=args.min_tasks,
                      minimums=read_json(args.minimums) if args.minimums else None)
        if args.out:
            write_json(args.out, result)
        markdown = compare_markdown(result)
        if args.markdown:
            args.markdown.parent.mkdir(parents=True, exist_ok=True)
            args.markdown.write_text(markdown, encoding="utf-8")
        print(markdown)
        return 0 if result["passed"] else 1
    if command == "roi":
        result = roi(read_json(args.profile), monthly_runs=args.monthly_runs, review_cost_eur=args.review_cost_eur,
                     max_monthly_loss_eur=args.max_monthly_loss_eur)
        if args.out:
            write_json(args.out, result)
        print(json.dumps(result, indent=2))
        return 0
    if command == "faults":
        result = [{"name": name, "category": category, "description": description} for name, (category, description) in CATALOG.items()]
        print(json.dumps(result, indent=2) if args.json else "\n".join(f"{r['name']:25} {r['category']:15} {r['description']}" for r in result))
        return 0
    if command == "proxy":
        from .proxy import make_proxy
        plan = ChaosPlan([Fault(args.fault)] if args.fault else [], seed=args.seed)
        server = make_proxy(args.upstream, store=Store(args.db), plan=plan, port=args.port, api_key=os.environ.get(args.api_key_env))
        print(f"Local JSON fault proxy: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    store = Store(args.db)
    if command == "import":
        print(f"Imported {store.import_jsonl(args.source)} runs")
    elif command == "export":
        count = store.export_parquet(args.out) if args.format == "parquet" else store.export_jsonl(args.out)
        print(f"Exported {count} runs to {args.out}")
    elif command == "list":
        print(json.dumps([{"id": r.run_id, "agent": r.agent, "task": r.task_id, "condition": r.condition, "success": r.success} for r in store.list(args.agent)], indent=2))
    elif command in {"show", "replay", "label"}:
        run = store.get(args.run_id)
        if command == "show":
            print(json.dumps(run.to_dict(), indent=2, ensure_ascii=False))
        elif command == "label":
            value = run.to_dict()
            value.update(success=args.success == "true", confidence=args.confidence,
                         harmful_actions=args.harmful_actions, loss_eur=args.loss_eur)
            run = Run.from_dict(value)
            run.metadata["verdict_source"] = "operator-cli"
            store.save(run)
            print(f"Labelled {run.run_id}")
        else:
            if not 1 <= args.times <= 1000:
                raise ValueError("times must be 1..1000")
            for _ in range(args.times):
                result = Replay(run).verify()
            print(json.dumps({**result, "identical_replays": args.times}, indent=2))
    else:
        runs = store.list(getattr(args, "agent", None))
        profiles = profiles_for(runs, args.bootstrap)
        if command == "score":
            write_json(args.out, profiles[0] if len(profiles) == 1 else profiles)
        elif command == "report":
            html_report(profiles, runs, args.out)
        elif command == "evidence":
            evidence_pack(runs, profiles, args.out)
        elif command == "site-data":
            from .privacy import scrub
            from collections import defaultdict
            groups = defaultdict(list)
            for run in runs:
                groups[(run.agent, run.condition)].append(run)
            conditions = [{"agent": a, "condition": c, "n": len(items),
                           "success_rate": sum(r.success for r in items) / len(items)}
                          for (a, c), items in sorted(groups.items())]
            # One trace per agent/task/condition keeps browser payload bounded.
            traces, seen = [], set()
            for run in runs:
                key = (run.agent, run.task_id, run.condition)
                if key not in seen:
                    traces.append(scrub(run.to_dict())[0])
                    seen.add(key)
            write_json(args.out, {"schema_version": 1, "generated_at": utcnow(), "profiles": profiles,
                                  "traces": traces, "conditions": conditions,
                                  "faults": [{"name": n, "category": c, "description": d} for n, (c, d) in CATALOG.items()],
                                  "disclosure": "Synthetic in-memory fixture agents. No third-party agents or live models have been rated."})
        print(str(args.out.resolve()))
    return 0


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        return dispatch(args)
    except (ValueError, TypeError, KeyError, RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"pruefstand: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
