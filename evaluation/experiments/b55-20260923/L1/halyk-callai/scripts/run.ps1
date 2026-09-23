param([ValidateSet('serve','test','validate','compile','baseline')][string]$Mode='serve')
$ErrorActionPreference='Stop'
$projectRoot=Split-Path $PSScriptRoot -Parent
$pythonPath=Join-Path $projectRoot '.venv/Scripts/python.exe'
Push-Location $projectRoot
try {
    if (-not(Test-Path -LiteralPath $pythonPath)) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
    }
    & $pythonPath -m pip install -e '.[test]' -c requirements.lock --disable-pip-version-check
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    switch ($Mode) {
        'serve' { & $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000 }
        'test' { & $pythonPath -m pytest -q }
        'validate' { & $pythonPath scripts/validate_dataset.py --output evaluation/results/dataset_validation.json }
        'compile' { & $pythonPath -m app.catalog.compiler }
        'baseline' { & $pythonPath evaluation/run_official.py }
    }
    $resultCode=$LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
