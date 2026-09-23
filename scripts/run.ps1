param([ValidateSet('serve','demo','test','validate','compile','baseline')][string]$Mode='serve')
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
        { $_ -in 'serve','demo' } {
            Push-Location (Join-Path $projectRoot 'frontend')
            try {
                if (-not (Test-Path 'node_modules')) { npm ci --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Frontend install failed' } }
                npm run build
                if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' }
            } finally { Pop-Location }
            $logRoot=Join-Path $projectRoot 'backend/runtime'
            New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
            $backendProcess=Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','app.main:app','--host','127.0.0.1','--port','8000' -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logRoot 'server.out.log') -RedirectStandardError (Join-Path $logRoot 'server.err.log')
            try {
                $ready=$false
                for ($i=0; $i -lt 30; $i++) {
                    if ($backendProcess.HasExited) { throw 'Backend exited; inspect backend/runtime/server.err.log' }
                    try { $health=Invoke-RestMethod 'http://127.0.0.1:8000/health'; $ready=($health.routing -eq 'golden-L2') } catch { $ready=$false }
                    if ($ready) { break }
                    Start-Sleep -Milliseconds 500
                }
                if (-not $ready) { throw 'Backend did not become ready' }
                Write-Host 'Halyk CallAI: http://127.0.0.1:3000 | Supervisor: http://127.0.0.1:3000/supervisor'
                Push-Location (Join-Path $projectRoot 'frontend')
                try { npm run start } finally { Pop-Location }
            } finally { if (-not $backendProcess.HasExited) { Stop-Process -Id $backendProcess.Id } }
        }
        'test' {
            & $pythonPath -m pytest -q
            if ($LASTEXITCODE -ne 0) { throw 'Backend tests failed' }
            Push-Location (Join-Path $projectRoot 'frontend')
            try { npm test; if ($LASTEXITCODE -ne 0) { throw 'Frontend tests failed' } } finally { Pop-Location }
        }
        'validate' { & $pythonPath scripts/validate_dataset.py --output evaluation/results/dataset_validation.json }
        'compile' { & $pythonPath -m app.catalog.compiler }
        'baseline' { & $pythonPath evaluation/run_official.py }
    }
    $resultCode=$LASTEXITCODE
} finally { Pop-Location }
exit $resultCode
