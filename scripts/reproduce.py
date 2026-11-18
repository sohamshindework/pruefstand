"""Regenerate explicit fixture experiment artifacts. Baseline updates require review."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    for command in [
        ["run", "--repeats", "5", "--seed", "42", "--out", "artifacts/release"],
        ["site-data", "--db", "artifacts/release/traces.db", "--out", "ratings/dist/data.json"],
    ]:
        subprocess.run([sys.executable, "-m", "pruefstand", *command], cwd=ROOT, check=True)
    import shutil
    shutil.copyfile(ROOT / "artifacts/release/profiles/idempotent-agent.json", ROOT / "benchmarks/baseline.json")
    shutil.copyfile(ROOT / "artifacts/release/profiles/vulnerable-retry.json", ROOT / "benchmarks/vulnerable.json")
    from pruefstand.faults import CATALOG
    from pruefstand.reports import write_json
    write_json(ROOT / "benchmarks/crashbench-v1.json", {"version": "1.0.0", "synthetic": True, "seed": 42,
        "repeats": 5, "tasks": "src/pruefstand/data/enterprise-de.json",
        "agents": ["vulnerable-retry", "idempotent-agent"],
        "conditions": ["baseline", *CATALOG],
        "faults": [{"name": n, "category": c, "description": d} for n, (c, d) in CATALOG.items()]})
    print("Regenerated synthetic dashboard data and baselines. Review baseline diffs before committing.")


if __name__ == "__main__":
    main()
