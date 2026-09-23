from app.catalog.compiler import compile_catalog, compact_text, catalog_hash


def test_complete_catalog_and_directional_boundaries(dataset):
    result = compile_catalog(dataset)
    assert {s["scenario_id"] for s in result["scenarios"]} == set(dataset.scenarios)
    assert len(result["system_intents"]) == 3
    assert len(result["boundary_rules"]) == 63
    assert len({r["rule_id"] for r in result["boundary_rules"]}) == 63
    for rule in result["boundary_rules"]:
        source = dataset.scenarios[rule["scenario_id"]]
        assert {"condition": rule["condition"], "use_instead": rule["neighbor_id"]} in source["not_this_if"]


def test_no_eval_gold_or_official_examples_in_compiled_prompt(dataset):
    text = compact_text(compile_catalog(dataset))
    assert '"expected"' not in text
    assert '"examples"' not in text
    assert '"U001"' not in text
    assert '"D01"' not in text


def test_reproducible_compilation(dataset):
    assert catalog_hash(compile_catalog(dataset)) == catalog_hash(compile_catalog(dataset))
    assert compile_catalog(dataset)["as_of_date"] == "2026-10-01"
