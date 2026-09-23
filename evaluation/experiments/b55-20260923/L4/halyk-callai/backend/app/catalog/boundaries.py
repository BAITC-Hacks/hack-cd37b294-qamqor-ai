from app.catalog.loader import Dataset


def compile_boundaries(dataset: Dataset) -> list[dict]:
    """Keep directional exceptions; never invent the reverse condition."""
    return [
        {"rule_id": f"scenarios.json#/scenarios/{index}/not_this_if/{number}",
         "scenario_id": scenario["scenario_id"], "neighbor_id": edge["use_instead"],
         "condition": edge["condition"]}
        for index, scenario in enumerate(dataset.documents["scenarios.json"]["scenarios"])
        for number, edge in enumerate(scenario["not_this_if"])
    ]
