import copy
import json
import pytest
from app.catalog.loader import DatasetError, load_dataset, unique_object, validate_dataset


def test_official_dataset_is_valid(dataset):
    report = validate_dataset(dataset)
    assert report["valid"], report["errors"]
    assert report["counts"]["official_examples"] == 104
    assert any("D01" in warning for warning in report["warnings"])


@pytest.mark.parametrize("mutation,fragment", [
    (lambda d: d["scenarios.json"]["scenarios"].append(d["scenarios.json"]["scenarios"][0]), "duplicate IDs"),
    (lambda d: d["scenarios.json"]["scenarios"][0]["actions"].append("invented"), "unknown action"),
    (lambda d: d["scenarios.json"]["scenarios"][0]["slots"]["required"].append("invented"), "unknown slot"),
    (lambda d: d["scenarios.json"]["scenarios"][0]["not_this_if"][0].update(use_instead="SC99"), "boundary target"),
    (lambda d: d["mock_backend.json"]["policies"][0].update(client_id="C999"), "unknown client"),
    (lambda d: d["dev_utterances.json"]["utterances"][0].update(expected=["SYS_OOS"]), "gold ID"),
])
def test_corruption_rejected(dataset, mutation, fragment):
    corrupted = copy.deepcopy(dataset)
    mutation(corrupted.documents)
    report = validate_dataset(corrupted)
    assert not report["valid"]
    assert any(fragment in e for e in report["errors"])


def test_duplicate_json_keys_rejected():
    with pytest.raises(DatasetError):
        json.loads('{"id":1,"id":2}', object_pairs_hook=unique_object)


def test_missing_input_fails(tmp_path):
    with pytest.raises(DatasetError):
        load_dataset(tmp_path)


def test_malformed_row_has_validation_report_not_traceback(dataset):
    corrupted = copy.deepcopy(dataset)
    corrupted.documents["scenarios.json"]["scenarios"][0] = "not an object"
    report = validate_dataset(corrupted)
    assert not report["valid"]
    assert "Malformed dataset structure" in report["errors"][0]
