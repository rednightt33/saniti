param(
    [string]$RuntimeRoot = $PSScriptRoot,
    [string]$ProjectId = '8aef1702-030b-49cb-9df7-5ac2e0a42691',
    [string]$EnvironmentId = '4d3e5af2-302b-4a2e-84e2-7d7476d6ff49',
    [string]$ServiceId = 'bb21a9f4-a9d3-4a51-945f-fa86b63f4b86',
    [string]$NpmCachePath = '',
    [string]$SslCertFile = '',
    [switch]$PlanOnly
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($env:STOCKBIT_TOKEN)) {
    throw 'STOCKBIT_TOKEN is missing. Set it only in the current PowerShell session before starting.'
}

$pythonPath = Join-Path $RuntimeRoot '.venv\Scripts\python.exe'
$runnerPath = Join-Path $RuntimeRoot 'stockbit_marketwide_broker_activity.py'
$supervisorPath = Join-Path $RuntimeRoot 'run_stockbit_backfill_background.ps1'
$outputDirectory = Join-Path $RuntimeRoot 'outputs'

foreach ($requiredPath in @($pythonPath, $runnerPath, $supervisorPath)) {
    if (-not (Test-Path -LiteralPath $requiredPath)) {
        throw "Required runner file not found: $requiredPath"
    }
}

if ([string]::IsNullOrWhiteSpace($NpmCachePath)) {
    $NpmCachePath = Join-Path (Split-Path $RuntimeRoot -Parent) 'npm-cache'
}
if ([string]::IsNullOrWhiteSpace($SslCertFile)) {
    $SslCertFile = Join-Path (Split-Path $RuntimeRoot -Parent) 'avast-root-ca.pem'
}

$runs = @(
    [ordered]@{ Name = 'historical-2025-2021'; StateDirectory = 'historical'; StatusStem = 'historical'; FromDate = '2021-01-01'; ToDate = '2025-08-31'; Workers = 3 },
    [ordered]@{ Name = 'historical-2018-2020'; StateDirectory = 'historical-2018-2020'; StatusStem = 'historical-2018-2020'; FromDate = '2018-01-01'; ToDate = '2020-12-31'; Workers = 3 },
    [ordered]@{ Name = 'historical-2017'; StateDirectory = 'historical-2017'; StatusStem = 'historical-2017'; FromDate = '2017-01-01'; ToDate = '2017-12-31'; Workers = 1 },
    [ordered]@{ Name = 'historical-2016'; StateDirectory = 'historical-2016'; StatusStem = 'historical-2016'; FromDate = '2016-01-01'; ToDate = '2016-12-31'; Workers = 1 },
    [ordered]@{ Name = 'historical-2015'; StateDirectory = 'historical-2015'; StatusStem = 'historical-2015'; FromDate = '2015-01-01'; ToDate = '2015-12-31'; Workers = 1 }
)

$results = foreach ($run in $runs) {
    $stateDirectory = Join-Path (Join-Path $RuntimeRoot 'state') $run.StateDirectory
    New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
    New-Item -ItemType Directory -Path $outputDirectory -Force | Out-Null

    $supervisorStatusPath = Join-Path $stateDirectory "backfill.$($run.StatusStem).supervisor.status.json"
    $runnerStatusPath = Join-Path $stateDirectory "backfill.$($run.StatusStem).runner.status.json"
    $stdoutPath = Join-Path $stateDirectory "supervisor-$($run.Name).stdout.log"
    $stderrPath = Join-Path $stateDirectory "supervisor-$($run.Name).stderr.log"

    $existingPid = $null
    $existingStatus = $null
    $existingRunnerStatus = $null
    if (Test-Path -LiteralPath $supervisorStatusPath) {
        try {
            $existingStatus = Get-Content -LiteralPath $supervisorStatusPath -Raw | ConvertFrom-Json
            $existingPid = $existingStatus.supervisor_pid
        }
        catch {
            $existingPid = $null
        }
    }
    if (Test-Path -LiteralPath $runnerStatusPath) {
        try {
            $existingRunnerStatus = Get-Content -LiteralPath $runnerStatusPath -Raw | ConvertFrom-Json
        }
        catch {
            $existingRunnerStatus = $null
        }
    }
    if ($existingRunnerStatus.state -eq 'COMPLETED') {
        [pscustomobject]@{
            Name = $run.Name
            FromDate = $run.FromDate
            ToDate = $run.ToDate
            Workers = $run.Workers
            State = 'SKIPPED_COMPLETED'
            SupervisorPid = $null
        }
        continue
    }
    $activeSupervisorStates = @('CONNECTING', 'RUNNING', 'RETRY_WAIT')
    $existingProcess = if ($existingPid) { Get-Process -Id $existingPid -ErrorAction SilentlyContinue } else { $null }
    if ($existingStatus.state -in $activeSupervisorStates -and $existingProcess.ProcessName -eq 'powershell') {
        [pscustomobject]@{
            Name = $run.Name
            FromDate = $run.FromDate
            ToDate = $run.ToDate
            Workers = $run.Workers
            State = 'ALREADY_RUNNING'
            SupervisorPid = $existingPid
        }
        continue
    }

    if ($PlanOnly.IsPresent) {
        [pscustomobject]@{
            Name = $run.Name
            FromDate = $run.FromDate
            ToDate = $run.ToDate
            Workers = $run.Workers
            State = 'PLANNED'
            SupervisorPid = $null
        }
        continue
    }

    $arguments = @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $supervisorPath,
        '-PythonPath', $pythonPath,
        '-RunnerPath', $runnerPath,
        '-OutputDirectory', $outputDirectory,
        '-StatusPath', $supervisorStatusPath,
        '-RunnerStatusPath', $runnerStatusPath,
        '-ProjectId', $ProjectId,
        '-EnvironmentId', $EnvironmentId,
        '-ServiceId', $ServiceId,
        '-FromDate', $run.FromDate,
        '-ToDate', $run.ToDate,
        '-DateOrder', 'descending',
        '-NoDailyExport',
        '-Workers', $run.Workers,
        '-AuthenticationFailureLimit', 5,
        '-NpmCachePath', $NpmCachePath,
        '-SslCertFile', $SslCertFile
    )

    $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath `
        -WindowStyle Hidden -PassThru

    [pscustomobject]@{
        Name = $run.Name
        FromDate = $run.FromDate
        ToDate = $run.ToDate
        Workers = $run.Workers
        State = 'STARTED'
        SupervisorPid = $process.Id
    }
}

$results
