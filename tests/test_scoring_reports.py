import hashlib
import json
import zipfile
from dataclasses import replace

import pytest

from pruefstand import Recorder
from pruefstand.german import check_german, parse_amount
from pruefstand.privacy import endpoint_assessment, scrub
from pruefstand.reports import evidence_pack, html_report, roi
from pruefstand.runner import SuiteConfig, run_suite
from pruefstand.scenarios import load_tasks
from pruefstand.scoring import calibrate_judge, gate, profile


@pytest.fixture
def experiment():
    return run_suite(tasks=load_tasks()[:3], faults=["timeout_after", "prompt_injection"], config=SuiteConfig(repeats=2))


def test_scores_intervals_and_gate_find_regression(experiment):
    vulnerable = profile([r for r in experiment if r.agent == "vulnerable-retry"], iterations=100)
    robust = profile([r for r in experiment if r.agent == "idempotent-agent"], iterations=100)
    assert robust["metrics"]["consistency"]["value"] == 1
    assert robust["metrics"]["robustness"]["value"] == 1
    assert vulnerable["metrics"]["robustness"]["value"] == 0
    assert robust["metrics"]["safety"]["value"] == 1
    assert vulnerable["metrics"]["safety"]["value"] == pytest.approx(1 / 3)
    assert robust == profile([r for r in experiment if r.agent == "idempotent-agent"], iterations=100)
    for metric in robust["metrics"].values():
        assert 0 <= metric["ci95"][0] <= metric["value"] <= metric["ci95"][1] <= 1
    assert gate(vulnerable, robust, min_runs=10)["passed"]
    assert not gate(robust, vulnerable, min_runs=10)["passed"]
    changed = {**robust, "comparison_key": "different"}
    assert not gate(robust, changed, min_runs=10)["passed"]
    assert not gate(robust, robust, min_runs=10000)["passed"]


def test_missing_measurements_are_unavailable_not_perfect():
    recorder = Recorder("a", "one")
    run = recorder.finish(success=True)
    p = profile([run], iterations=100)
    assert p["metrics"]["consistency"]["value"] is None
    assert p["metrics"]["predictability"]["value"] is None
    assert p["metrics"]["robustness"]["value"] is None
    assert not gate(p, p, min_runs=1, min_tasks=1)["passed"]
    assert len(p["warnings"]) >= 2
    with pytest.raises(ValueError):
        profile([replace(run, success=None)], iterations=100)
    with pytest.raises(ValueError):
        profile([run, replace(run, agent="b")], iterations=100)


def test_consistently_wrong_does_not_earn_consistency():
    run = Recorder("a", "task").finish(success=False)
    assert profile([run, replace(run, run_id="other")], iterations=100)["metrics"]["consistency"]["value"] == 0


def test_calibration_uses_probabilities_and_held_out_labels():
    perfect = calibrate_judge([0, 1, 1, 0], [False, True, True, False])
    assert perfect["brier"] == perfect["expected_calibration_error"] == 0
    assert calibrate_judge([1, 0], [False, True])["brier"] == 1
    with pytest.raises(ValueError):
        calibrate_judge([1.5], [True])


def test_privacy_is_nested_and_never_includes_matched_text_in_findings():
    source = {"authorization": "Bearer secret", "customer": {"email": "test@example.test", "details": "DE89370400440532013000; Musterstraße 12; Diagnose Diabetes; 12345678901"}}
    cleaned, findings = scrub(source)
    assert source["authorization"] == "Bearer secret"
    assert "test@example.test" not in json.dumps(cleaned)
    assert "DE89370400440532013000" not in json.dumps(cleaned)
    assert "test@example.test" not in json.dumps(findings)
    assert {f["category"] for f in findings} >= {"secret", "email", "iban", "german_address_candidate", "health_data_candidate"}
    assert not endpoint_assessment("https://api.example.test", ["other.test"])["declared_eu"]
    assert not endpoint_assessment("https://api.example.test", ["api.example.test"])["verified_residency"]


def test_german_amounts_formality_and_disclosure():
    assert str(parse_amount("1.234,56 €")) == "1234.56"
    assert str(parse_amount("-1.234,56 EUR")) == "-1234.56"
    with pytest.raises(ValueError):
        parse_amount("1,234.56")
    assert check_german("Ich bin Ihr KI-Assistent. Sie erhalten 1.234,56 € am 18.11.2026.", amount="1.234,56 €", date="18.11.2026", disclosure=True)["passed"]
    assert not check_german("Du erhältst 1234.56 EUR.", amount="1.234,56 €")["passed"]


def test_evidence_integrity_privacy_and_roi(experiment, tmp_path):
    profiles = [profile([r for r in experiment if r.agent == a], iterations=100) for a in ("vulnerable-retry", "idempotent-agent")]
    path = evidence_pack(experiment, profiles, tmp_path / "evidence.zip")
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert all(hashlib.sha256(archive.read(name)).hexdigest() == digest for name, digest in manifest.items())
        assert "not legal advice" in json.loads(archive.read("evidence.json"))["scope"]
    risk = roi(profiles[0], monthly_runs=100)
    assert risk["recommendation"] == "NO-GO"
    assert roi(profiles[1], monthly_runs=100)["projected_monthly_loss_eur"] == 0


def test_html_escapes_user_controlled_values(tmp_path):
    recorder = Recorder('<script>alert(1)</script>', "task")
    run = recorder.finish(success=True, output="<img src=x onerror=alert(1)>")
    p = profile([run], iterations=100)
    path = html_report([p], [run], tmp_path / "report.html")
    source = path.read_text()
    assert "<script>alert" not in source
    assert "<img src=x" not in source
    assert "&lt;script&gt;" in source
