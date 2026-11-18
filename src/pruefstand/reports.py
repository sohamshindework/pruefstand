"""Portable HTML, euro-impact scenarios, and integrity-manifest evidence archives."""

from __future__ import annotations

import hashlib
import html
import json
import zipfile
from pathlib import Path

from .privacy import scrub
from .schema import Run, canonical, finite, utcnow


def write_json(path: str | Path, value) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    return path


def roi(profile: dict, *, monthly_runs: int = 50_000, review_cost_eur: float = 2,
        max_monthly_loss_eur: float = 1000) -> dict:
    if monthly_runs < 1:
        raise ValueError("monthly_runs must be positive")
    finite(review_cost_eur, "review_cost_eur")
    finite(max_monthly_loss_eur, "max_monthly_loss_eur")
    failure = 1 - profile["metrics"]["success_rate"]["value"]
    loss = monthly_runs * profile["mean_loss_eur"]
    review = monthly_runs * failure * review_cost_eur
    return {"monthly_runs": monthly_runs, "projected_monthly_loss_eur": loss,
            "loss_ci95_eur": [monthly_runs * v for v in profile["mean_loss_ci95"]],
            "projected_review_cost_eur": review, "combined_scenario_cost_eur": loss + review,
            "max_monthly_loss_eur": max_monthly_loss_eur,
            "recommendation": "REVIEW" if loss <= max_monthly_loss_eur and profile["harmful_runs"] == 0 else "NO-GO",
            "assumptions": ["Test fault frequency is assumed to match production; reweight before business use.",
                            "Observed losses and review costs are additive scenario inputs, not a causal ROI estimate.",
                            "A passing experiment is not an authorization to deploy."],
            "synthetic": profile["synthetic"]}


def html_report(profiles: list[dict], runs: list[Run], path: str | Path) -> Path:
    def escape(value):
        return html.escape(str(value), quote=True)
    cards = []
    for p in profiles:
        rows = "".join(f"<tr><td>{escape(name.replace('_', ' ').title())}</td><td>{'N/A' if metric['value'] is None else format(metric['value'], '.3f')}</td><td>{escape(metric['ci95'])}</td></tr>" for name, metric in p["metrics"].items())
        cards.append(f"<section><h2>{escape(p['agent'])}</h2><p>{p['n_runs']} runs · {p['n_tasks']} tasks · {'SYNTHETIC FIXTURE' if p['synthetic'] else 'USER-SUPPLIED EXPERIMENT'}</p><table><tr><th>Dimension</th><th>Score</th><th>95% task-bootstrap interval</th></tr>{rows}</table><p>Observed harmful runs: {p['harmful_runs']} · p95: {p['latency_ms']['p95']:.2f} ms</p><ul>{''.join('<li>'+escape(w)+'</li>' for w in p['warnings'])}</ul></section>")
    trace_rows = []
    for run in runs[:100]:
        safe = scrub(run.to_dict())[0]
        trace_rows.append(f"<details><summary>{escape(run.agent)} / {escape(run.task_id)} / {escape(run.condition)} — {'PASS' if run.success else 'FAIL'}</summary><pre>{escape(json.dumps(safe, ensure_ascii=False, indent=2))}</pre></details>")
    text = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Prüfstand — Reliability Report</title><style>body{font:16px/1.6 system-ui;background:#101715;color:#e8eee8;max-width:1100px;margin:auto;padding:36px}h1{font-size:42px}section,details{background:#19241f;padding:20px;margin:20px 0;border:1px solid #3b4f40;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #3b4f40}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}p{color:#b8c9b9}summary{cursor:pointer}</style><h1>Prüfstand / Reliability Report</h1><p>Operational metrics v1. Four dimensions inspired by agent-reliability research; not the paper's complete metric implementation. Results are limited to the specified tasks and fault distribution.</p>""" + "".join(cards) + "<h2>Flight recorder</h2><p>First 100 runs. Sensitive patterns redacted; heuristic screening has false positives and false negatives.</p>" + "".join(trace_rows) + "</html>"
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def evidence_pack(runs: list[Run], profiles: list[dict], path: str | Path) -> Path:
    # Even raw-capture runs are screened again before evidence export.
    safe_runs = [scrub(r.to_dict())[0] for r in runs]
    evidence = {
        "title": "Prüfstand AI governance evidence pack", "generated_at": utcnow(),
        "scope": "Technical test evidence for human review; not legal advice or a compliance certification.",
        "controls": {
            "transparency": {"status": "review-required", "observations": [r.metadata.get("german_checks") for r in runs if r.metadata.get("german_checks")]},
            "human_oversight": {"status": "observed-only", "events": sum(e.kind == "oversight" for r in runs for e in r.events)},
            "robustness_accuracy": {"status": "tested-within-scope", "profile_count": len(profiles)},
            "data_screening": {"status": "heuristic", "finding_count": sum(len(e.privacy_findings) for r in runs for e in r.events)},
            "residency": {"status": "unverified", "note": "Endpoint declarations do not prove processing location or retention."},
        },
        "review_questions": ["Does the intended use trigger legal obligations?", "Are disclosure and oversight effective in the deployed product?", "Are retention, access, lawful basis and processing agreements documented?"],
    }
    files = {
        "evidence.json": canonical(evidence).encode(),
        "profiles.json": canonical(scrub(profiles)[0]).encode(),
        "traces.jsonl": ("\n".join(canonical(r) for r in safe_runs) + "\n").encode(),
        "README.txt": b"Technical evidence only. See evidence.json for scope and review questions. manifest.json contains SHA-256 hashes of these files. Traces may contain sensitive data not recognized by heuristic screening. Review before sharing.\n",
    }
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
        archive.writestr("manifest.json", canonical(manifest))
    return path
