import json
import io
import pytest
from evaluation.run_official import main
from evaluation.run_official import configure_console
from evaluation.recover_report import recover


def test_missing_key_never_fabricates_predictions_or_scores(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("CALLAI_DATASET_PATH", raising=False)
    rc = main(["--env-file", str(tmp_path / "absent.env"), "--output-dir", str(tmp_path / "results")])
    assert rc == 2
    report = json.loads((tmp_path / "results" / "baseline.json").read_text(encoding="utf-8"))
    assert report["status"] == "blocked" and report["metrics"] is None
    assert report["official_examples"] == 104
    assert not list(tmp_path.rglob("predictions.json"))
    assert not list(tmp_path.rglob("official_stdout.txt"))


def test_failed_attempt_preserves_previous_measured_baseline(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.delenv("CALLAI_DATASET_PATH", raising=False)
    target = tmp_path / "baseline.json"
    sentinel = '{"status":"executed","unit_fixture": "previous baseline must remain byte-identical"}'
    target.write_text(sentinel, encoding="utf-8")
    assert main(["--env-file", str(tmp_path / "absent.env"), "--output-dir", str(tmp_path)]) == 2
    assert target.read_text(encoding="utf-8") == sentinel
    assert json.loads((tmp_path / "last_attempt.json").read_text())["status"] == "blocked"


def test_kazakh_console_output_works_on_windows_encoding():
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1251")
    configure_console(stream)
    stream.write("Көлікті бағалау")
    stream.flush()
    assert buffer.getvalue().decode("utf-8") == "Көлікті бағалау"


def test_report_recovery_rejects_partial_run(dataset, tmp_path):
    (tmp_path / "metadata.json").write_text(json.dumps({"source_hashes": dataset.hashes}), encoding="utf-8")
    (tmp_path / "raw.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="exactly one"):
        recover(tmp_path, dataset)


def test_report_recovery_rejects_changed_gold(dataset, tmp_path):
    (tmp_path / "metadata.json").write_text('{"source_hashes":{}}', encoding="utf-8")
    with pytest.raises(ValueError, match="sources differ"):
        recover(tmp_path, dataset)
