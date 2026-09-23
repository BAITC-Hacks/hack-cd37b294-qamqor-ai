.PHONY: install serve test validate compile baseline
install:
	python -m pip install -e '.[test]' -c requirements.lock
serve:
	python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
test:
	python -m pytest -q
validate:
	python scripts/validate_dataset.py --output evaluation/results/dataset_validation.json
compile:
	python -m app.catalog.compiler
baseline:
	python evaluation/run_official.py
