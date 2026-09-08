param(
    [Parameter(Mandatory = $true)] [string]$PythonPath,
    [Parameter(Mandatory = $true)] [string]$RunnerPath,
    [Parameter(Mandatory = $true)] [string]$OutputDirectory,
    [Parameter(Mandatory = $true)] [string]$StatusPath,
    [Parameter(Mandatory = $true)] [string]$RunnerStatusPath,
    [Parameter(Mandatory = $true)] [string]$ProjectId,
    [Parameter(Mandatory = $true)] [string]$EnvironmentId,
    [Parameter(Mandatory = $true)] [string]$ServiceId,
    [string]$FromDate = '2025-11-17',
    [string]$ToDate = '2026-08-31',
    [ValidateSet('ascending', 'descending')] [string]$DateOrder = 'ascending',
    [switch]$NoDailyExport,
    [int]$Workers = 6,
    [int]$DateRetries = 3,
    [int]$AuthenticationFailureLimit = 5,
    [int]$DateRetryBaseSeconds = 30,
    [int]$SupervisorRetryBaseSeconds = 30,
    [int]$SupervisorRetryMaxSeconds = 600,
    [string]$NpmCachePath = '',
    [string]$SslCertFile = ''
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

function Write-SupervisorStatus {
    param(
        [Parameter(Mandatory = $true)] [string]$State,
        [int]$Cycle,
        [int]$ExitCode = -1,
        [string]$Message = '',
        [string]$ProxyId = '',
        [int]$RetryInSeconds = 0
    )
    $status = [ordered]@{
        state = $State
        supervisor_pid = $PID
        cycle = $Cycle
        from_date = $FromDate
        to_date = $ToDate
        date_order = $DateOrder
        daily_export_enabled = -not $NoDailyExport.IsPresent
        authentication_failure_limit = $AuthenticationFailureLimit
        proxy_id = $ProxyId
        exit_code = $ExitCode
        retry_in_seconds = $RetryInSeconds
        message = $Message
        updated_at = [DateTimeOffset]::UtcNow.ToString('o')
    }
    $temporary = "$StatusPath.tmp"
    $status | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $StatusPath -Force
}

function Invoke-RailwayJson {
    param([Parameter(Mandatory = $true)] [string[]]$Arguments)
    $output = @(& npx.cmd -y '@railway/cli' @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw "Railway CLI failed: $($output -join ' ')"
    }
    $text = $output -join "`n"
    if ([string]::IsNullOrWhiteSpace($text)) { return $null }
    try {
        return $text | ConvertFrom-Json
    }
    catch {
        throw "Railway CLI returned invalid JSON: $text"
    }
}

function Get-PropertyValue {
    param(
        [Parameter(Mandatory = $true)] $Object,
        [Parameter(Mandatory = $true)] [string[]]$Names
    )
    foreach ($name in $Names) {
        $property = $Object.PSObject.Properties[$name]
        if ($null -ne $property -and $null -ne $property.Value -and "$($property.Value)" -ne '') {
            return $property.Value
        }
    }
    return $null
}

function Get-ProxyDetails {
    $list = Invoke-RailwayJson -Arguments @(
        'tcp-proxy', 'list', '--project', $ProjectId, '--environment', $EnvironmentId,
        '--service', $ServiceId, '--json'
    )
    $items = if ($null -ne $list.PSObject.Properties['proxies']) { @($list.proxies) } else { @($list) }
    foreach ($candidate in $items) {
        $applicationPort = Get-PropertyValue -Object $candidate -Names @('applicationPort', 'application_port', 'port')
        $domain = Get-PropertyValue -Object $candidate -Names @('domain', 'proxyDomain', 'proxy_domain')
        $proxyPort = Get-PropertyValue -Object $candidate -Names @('proxyPort', 'proxy_port')
        $id = Get-PropertyValue -Object $candidate -Names @('id', 'proxyId', 'proxy_id')
        if ([int]$applicationPort -eq 5432 -and $domain -and $proxyPort -and $id) {
            return [pscustomobject]@{ id = "$id"; domain = "$domain"; proxyPort = [int]$proxyPort }
        }
    }
    return $null
}

function Ensure-RailwayProxy {
    $proxy = Get-ProxyDetails
    if ($null -eq $proxy) {
        Invoke-RailwayJson -Arguments @(
            'tcp-proxy', 'create', '--project', $ProjectId, '--environment', $EnvironmentId,
            '--service', $ServiceId, '--port', '5432', '--json'
        ) | Out-Null
    }
    for ($attempt = 1; $attempt -le 18; $attempt++) {
        $proxy = Get-ProxyDetails
        if ($null -ne $proxy) { return $proxy }
        Start-Sleep -Seconds 5
    }
    throw 'Railway PostgreSQL TCP proxy did not become active within 90 seconds.'
}

function Remove-RailwayProxy {
    param([string]$ProxyId)
    if ([string]::IsNullOrWhiteSpace($ProxyId)) { return }
    Invoke-RailwayJson -Arguments @(
        'tcp-proxy', 'delete', $ProxyId, '--project', $ProjectId, '--environment', $EnvironmentId,
        '--service', $ServiceId, '--yes', '--json'
    ) | Out-Null
}

function Get-DatabaseUrl {
    param([Parameter(Mandatory = $true)] $Proxy)
    $variables = Invoke-RailwayJson -Arguments @(
        'variable', 'list', '--project', $ProjectId, '--environment', $EnvironmentId,
        '--service', $ServiceId, '--json'
    )
    $user = Get-PropertyValue -Object $variables -Names @('PGUSER', 'POSTGRES_USER')
    $password = Get-PropertyValue -Object $variables -Names @('PGPASSWORD', 'POSTGRES_PASSWORD')
    $database = Get-PropertyValue -Object $variables -Names @('PGDATABASE', 'POSTGRES_DB')
    if (-not $user -or -not $password -or -not $database) {
        throw 'Railway PostgreSQL variables are incomplete.'
    }
    $escapedUser = [Uri]::EscapeDataString("$user")
    $escapedPassword = [Uri]::EscapeDataString("$password")
    $escapedDatabase = [Uri]::EscapeDataString("$database")
    return "postgresql://${escapedUser}:${escapedPassword}@$($Proxy.domain):$($Proxy.proxyPort)/${escapedDatabase}?sslmode=require"
}

if ([string]::IsNullOrWhiteSpace($env:STOCKBIT_TOKEN)) {
    throw 'STOCKBIT_TOKEN is missing from the supervisor environment.'
}
# Railway CLI uses RAILWAY_TOKEN when supplied and otherwise falls back to the
# existing local Railway login session.

$env:NODE_OPTIONS = '--use-system-ca'
$env:RAILWAY_CALLER = 'skill:use-railway@1.4.0'
$env:RAILWAY_SESSION = 'broksum-supervisor-20260906'
if (-not [string]::IsNullOrWhiteSpace($NpmCachePath)) { $env:npm_config_cache = $NpmCachePath }
if (-not [string]::IsNullOrWhiteSpace($SslCertFile)) { $env:SSL_CERT_FILE = $SslCertFile }

$cycle = 0
$retrySeconds = [Math]::Max(1, $SupervisorRetryBaseSeconds)
$completed = $false
$currentProxyId = ''

try {
    while (-not $completed) {
        $cycle++
        try {
            Write-SupervisorStatus -State 'CONNECTING' -Cycle $cycle -ProxyId $currentProxyId
            $proxy = Ensure-RailwayProxy
            $currentProxyId = $proxy.id
            $env:DATABASE_URL = Get-DatabaseUrl -Proxy $proxy
            Write-SupervisorStatus -State 'RUNNING' -Cycle $cycle -ProxyId $currentProxyId

            $runnerArguments = @(
                '--from-date', $FromDate, '--to-date', $ToDate,
                '--date-order', $DateOrder, '--workers', "$Workers",
                '--date-retries', "$DateRetries", '--retry-base-seconds', "$DateRetryBaseSeconds",
                '--authentication-failure-limit', "$AuthenticationFailureLimit",
                '--status-file', $RunnerStatusPath, '--daily-output-dir', $OutputDirectory
            )
            if ($NoDailyExport.IsPresent) { $runnerArguments += '--no-daily-export' }
            & $PythonPath $RunnerPath @runnerArguments
            $exitCode = $LASTEXITCODE

            if ($exitCode -eq 0) {
                $completed = $true
                Write-SupervisorStatus -State 'COMPLETED' -Cycle $cycle -ExitCode 0 -ProxyId $currentProxyId
                break
            }

            if ($exitCode -eq 3) {
                Write-SupervisorStatus -State 'STOPPED_INVALID_TOKEN' -Cycle $cycle -ExitCode 3 `
                    -Message 'Stockbit authentication failed five consecutive times; query stopped.' `
                    -ProxyId $currentProxyId
                break
            }

            if ($exitCode -eq 1) {
                try {
                    Remove-RailwayProxy -ProxyId $currentProxyId
                    $currentProxyId = ''
                }
                catch {
                    Write-Warning "Unable to replace the failed proxy immediately: $($_.Exception.Message)"
                }
            }
            $message = if ($exitCode -eq 2) {
                'One or more dates need review; completed dates are preserved and failed dates will be retried.'
            } else {
                'The runner stopped unexpectedly; it will resume from the earliest incomplete date.'
            }
            Write-SupervisorStatus -State 'RETRY_WAIT' -Cycle $cycle -ExitCode $exitCode -Message $message -ProxyId $currentProxyId -RetryInSeconds $retrySeconds
        }
        catch {
            $message = $_.Exception.Message
            try {
                Remove-RailwayProxy -ProxyId $currentProxyId
                $currentProxyId = ''
            }
            catch {
                $message = "$message Proxy replacement cleanup also failed: $($_.Exception.Message)"
            }
            Write-SupervisorStatus -State 'RETRY_WAIT' -Cycle $cycle -ExitCode 1 -Message $message -ProxyId $currentProxyId -RetryInSeconds $retrySeconds
        }
        finally {
            Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds $retrySeconds
        $retrySeconds = [Math]::Min($SupervisorRetryMaxSeconds, $retrySeconds * 2)
    }
}
finally {
    if ($completed) {
        try { Remove-RailwayProxy -ProxyId $currentProxyId }
        catch {
            Write-SupervisorStatus -State 'CLEANUP_WARNING' -Cycle $cycle -ExitCode 0 -Message $_.Exception.Message -ProxyId $currentProxyId
        }
    }
    Remove-Item Env:STOCKBIT_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:RAILWAY_TOKEN -ErrorAction SilentlyContinue
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
}

exit 0
