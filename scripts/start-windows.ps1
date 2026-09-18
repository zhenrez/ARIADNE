[CmdletBinding()]
param(
    [int]$PreferredPort = 8765,
    [switch]$VerifyOnly,
    [switch]$NoBrowser,
    [ValidateSet('', '3.13', '3.11')]
    [string]$RequiredPythonMinor = ''
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$Root = Split-Path -Parent $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPython = Join-Path $Venv 'Scripts\python.exe'
$Requirements = Join-Path $Root 'requirements.txt'
$Artifacts = Join-Path $Root 'artifacts'
$FailureLog = Join-Path $Artifacts 'launcher-failure.txt'
$SuccessLog = Join-Path $Artifacts 'launcher-success.json'
$Server = $null
$StopRelative = "artifacts\launcher-stop-$PID.flag"
$StopFile = Join-Path $Root $StopRelative

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-ForbiddenPythonPath([string]$Path) {
    if ([string]::IsNullOrWhiteSpace($Path)) { return $true }
    return $Path -match '(?i)(conda|anaconda|miniconda|mambaforge|miniforge|nvidia|cuda|windowsapps|[\\/]\.venv[\\/]|[\\/]venv[\\/]|[\\/]envs?[\\/])'
}

function Test-PythonInfo([string]$Raw,[string]$ExpectedMinor,[string]$CandidateLabel) {
    if (-not $Raw) { return $null }
    try { $Info=$Raw | ConvertFrom-Json } catch {
        Write-Host "Rejected ${CandidateLabel}: probe output was not valid JSON." -ForegroundColor DarkYellow
        return $null
    }
    if ($Info.implementation -ne 'CPython') {
        Write-Host "Rejected ${CandidateLabel}: implementation is $($Info.implementation), not CPython." -ForegroundColor DarkYellow
        return $null
    }
    if ($Info.bits -ne 64) {
        Write-Host "Rejected ${CandidateLabel}: $($Info.bits)-bit runtime; 64-bit required." -ForegroundColor DarkYellow
        return $null
    }
    if ($Info.version -notmatch "^$([regex]::Escape($ExpectedMinor))\.") {
        Write-Host "Rejected ${CandidateLabel}: version $($Info.version) does not match $ExpectedMinor." -ForegroundColor DarkYellow
        return $null
    }
    foreach ($Field in @('executable','base_executable','base_prefix')) {
        if (Test-ForbiddenPythonPath ([string]$Info.$Field)) {
            Write-Host "Rejected ${CandidateLabel}: $Field points to a forbidden Python environment: $($Info.$Field)" -ForegroundColor DarkYellow
            return $null
        }
    }
    return $Info
}

function Probe-PyLauncher([string]$Launcher,[string]$ExpectedMinor) {
    $Probe='import json,platform,struct,sys; print(json.dumps({"version":platform.python_version(),"implementation":platform.python_implementation(),"bits":struct.calcsize("P")*8,"executable":sys.executable,"base_executable":getattr(sys,"_base_executable",sys.executable),"prefix":sys.prefix,"base_prefix":sys.base_prefix}))'
    $Selector="-$ExpectedMinor"
    try {
        $Raw=& $Launcher $Selector -I -c $Probe 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $Info=Test-PythonInfo -Raw $Raw -ExpectedMinor $ExpectedMinor -CandidateLabel "$Launcher $Selector"
        if (-not $Info) { return $null }
        return @{Command=$Launcher;Prefix=@($Selector);Version=[string]$Info.version;Minor=$ExpectedMinor;Executable=[string]$Info.executable;BaseExecutable=[string]$Info.base_executable}
    } catch { return $null }
}

function Probe-PythonExe([string]$Path,[string]$ExpectedMinor) {
    $Probe='import json,platform,struct,sys; print(json.dumps({"version":platform.python_version(),"implementation":platform.python_implementation(),"bits":struct.calcsize("P")*8,"executable":sys.executable,"base_executable":getattr(sys,"_base_executable",sys.executable),"prefix":sys.prefix,"base_prefix":sys.base_prefix}))'
    try {
        $Raw=& $Path -I -c $Probe 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        $Info=Test-PythonInfo -Raw $Raw -ExpectedMinor $ExpectedMinor -CandidateLabel $Path
        if (-not $Info) { return $null }
        return @{Command=$Path;Prefix=@();Version=[string]$Info.version;Minor=$ExpectedMinor;Executable=[string]$Info.executable;BaseExecutable=[string]$Info.base_executable}
    } catch { return $null }
}

function Select-BasePython {
    $Minors = if ($RequiredPythonMinor) { @($RequiredPythonMinor) } else { @('3.13', '3.11') }
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        foreach ($Minor in $Minors) {
            $Candidate = Probe-PyLauncher -Launcher $Launcher.Source -ExpectedMinor $Minor
            if ($Candidate) { return $Candidate }
        }
    }

    $Known = @()
    foreach ($Minor in $Minors) {
        $Compact = $Minor.Replace('.', '')
        if ($env:LocalAppData) { $Known += (Join-Path $env:LocalAppData "Programs\Python\Python$Compact\python.exe") }
        if ($env:ProgramFiles) { $Known += (Join-Path $env:ProgramFiles "Python$Compact\python.exe") }
        $Known += "C:\Python$Compact\python.exe"
    }
    foreach ($Path in $Known | Select-Object -Unique) {
        if (Test-Path -LiteralPath $Path) {
            foreach ($Minor in $Minors) {
                $Candidate = Probe-PythonExe -Path $Path -ExpectedMinor $Minor
                if ($Candidate) { return $Candidate }
            }
        }
    }

    foreach ($Command in @(Get-Command python.exe -All -ErrorAction SilentlyContinue)) {
        if (Test-ForbiddenPythonPath $Command.Source) { continue }
        foreach ($Minor in $Minors) {
            $Candidate = Probe-PythonExe -Path $Command.Source -ExpectedMinor $Minor
            if ($Candidate) { return $Candidate }
        }
    }

    $Wanted = if ($RequiredPythonMinor) { $RequiredPythonMinor } else { '3.13 or 3.11' }
    throw @"
No clean 64-bit CPython $Wanted installation was found.

ARIADNE deliberately refused NVIDIA, CUDA, Conda, Anaconda, Miniconda,
Miniforge/Mambaforge, Windows Store aliases, and unrelated virtual environments.

Install the official 64-bit CPython build from python.org with the Python
Launcher enabled, then double-click START-ARIADNE.cmd again.
"@
}

function Clear-ContaminatingEnvironment {
    Get-ChildItem Env: | Where-Object {
        $_.Name -match '^(PYTHON|PYLAUNCHER|CONDA|_CONDA|VIRTUAL_ENV|PIPENV|POETRY|UV_|CUDA|NVIDIA|MAMBA|MICROMAMBA|PYENV|PIP_)'
    } | ForEach-Object { Remove-Item "Env:$($_.Name)" -ErrorAction SilentlyContinue }

    foreach ($Name in @('SSL_CERT_FILE', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE')) {
        $Value = [Environment]::GetEnvironmentVariable($Name)
        if ($Value -and (Test-ForbiddenPythonPath $Value)) { Remove-Item "Env:$Name" -ErrorAction SilentlyContinue }
    }

    $SafePath = New-Object System.Collections.Generic.List[string]
    foreach ($Entry in ($env:PATH -split ';')) {
        if ([string]::IsNullOrWhiteSpace($Entry)) { continue }
        if ($Entry -match '(?i)(python|conda|anaconda|miniconda|miniforge|mambaforge|nvidia|cuda|[\\/]\.venv([\\/]|$)|[\\/]venv([\\/]|$)|[\\/]envs?([\\/]|$))') { continue }
        if (-not $SafePath.Contains($Entry)) { $SafePath.Add($Entry) }
    }

    $env:PATH = (@((Join-Path $Venv 'Scripts')) + @($SafePath)) -join ';'
    $env:VIRTUAL_ENV = $Venv
    $env:PYTHONNOUSERSITE = '1'
    $env:PYTHONPATH = ''
    $env:PYTHONUTF8 = '1'
    $env:PIP_CONFIG_FILE = 'NUL'
    $env:PIP_DISABLE_PIP_VERSION_CHECK = '1'
    $env:PIP_NO_INPUT = '1'
}

function Get-OpenPort([int]$Start) {
    for ($Port=$Start; $Port -le ($Start+100); $Port++) {
        $Listener=[System.Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback,$Port)
        try { $Listener.Start(); return $Port } catch {} finally { try {$Listener.Stop()} catch {} }
    }
    throw "No available localhost port was found between $Start and $($Start+100)."
}

function Find-ExistingAriadne([int]$Start) {
    $ExpectedRoot=[IO.Path]::GetFullPath($Root).TrimEnd('\')
    for ($Port=$Start; $Port -le ($Start+30); $Port++) {
        try {
            $Health=Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/health" -TimeoutSec 1
            if ($Health.service -eq 'ARIADNE') {
                $ActualRoot=[IO.Path]::GetFullPath([string]$Health.root).TrimEnd('\')
                if ($ActualRoot -ieq $ExpectedRoot) { return @{Port=$Port;Health=$Health} }
            }
        } catch {}
    }
    return $null
}

function Test-Venv([hashtable]$Base) {
    if (-not (Test-Path -LiteralPath $VenvPython)) { return $false }
    $Probe='import json,platform,struct,sys; print(json.dumps({"version":platform.python_version(),"implementation":platform.python_implementation(),"bits":struct.calcsize("P")*8,"base_executable":getattr(sys,"_base_executable",sys.executable),"prefix":sys.prefix,"base_prefix":sys.base_prefix}))'
    try {
        $Raw=& $VenvPython -I -c $Probe 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $Raw) { return $false }
        $Info=$Raw | ConvertFrom-Json
        if ($Info.implementation -ne 'CPython' -or $Info.bits -ne 64) { return $false }
        if ($Info.version -notmatch "^$([regex]::Escape($Base.Minor))\.") { return $false }
        if (Test-ForbiddenPythonPath $Info.base_executable) { return $false }
        if (Test-ForbiddenPythonPath $Info.base_prefix) { return $false }
        $ExpectedPrefix=[IO.Path]::GetFullPath($Venv).TrimEnd('\')
        $ActualPrefix=[IO.Path]::GetFullPath([string]$Info.prefix).TrimEnd('\')
        return $ActualPrefix -ieq $ExpectedPrefix
    } catch { return $false }
}

function Remove-IncompatibleVenv {
    if (-not (Test-Path -LiteralPath $Venv)) { return }
    Write-Step 'Replacing an incompatible or externally managed .venv'
    try { Remove-Item -LiteralPath $Venv -Recurse -Force }
    catch {
        throw @"
ARIADNE could not replace the existing .venv because Windows says one of its
files is still in use. Close any older ARIADNE/Python window using this folder,
then double-click START-ARIADNE.cmd again.

Nothing outside this repository was changed.
"@
    }
}

function Wait-ForHealth([System.Diagnostics.Process]$Process,[int]$Port) {
    $Url="http://127.0.0.1:$Port/"
    for ($Attempt=0;$Attempt -lt 100;$Attempt++) {
        $Process.Refresh()
        if ($Process.HasExited) { throw "ARIADNE stopped during startup with exit code $($Process.ExitCode)." }
        try {
            $Health=Invoke-RestMethod -Uri ($Url+'api/health') -TimeoutSec 1
            if ($Health.service -eq 'ARIADNE' -and $Health.status -eq 'ok') { return $Url }
        } catch {}
        Start-Sleep -Milliseconds 100
    }
    throw 'ARIADNE did not become ready within ten seconds.'
}

function Stop-AriadneServer {
    if ($null -eq $Server) { return }
    $Server.Refresh()
    if ($Server.HasExited) { return }
    try { Set-Content -LiteralPath $StopFile -Value 'stop' -Encoding ASCII } catch {}
    for ($Attempt=0;$Attempt -lt 100;$Attempt++) {
        $Server.Refresh()
        if ($Server.HasExited) { break }
        Start-Sleep -Milliseconds 100
    }
    $Server.Refresh()
    if (-not $Server.HasExited) { Stop-Process -Id $Server.Id -Force -ErrorAction SilentlyContinue }
}

function Write-Failure([System.Management.Automation.ErrorRecord]$Failure) {
    try { New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null } catch {}
    $Lines=@(
        'ARIADNE launcher failure',
        ('Time: '+[DateTime]::UtcNow.ToString('o')),
        ('Root: '+$Root),
        ('Message: '+$Failure.Exception.Message),
        ('Position: '+$Failure.InvocationInfo.PositionMessage),
        ('Script stack: '+$Failure.ScriptStackTrace),
        '',
        'No global Python, CUDA, NVIDIA, Conda, or Anaconda installation was changed.'
    )
    try { Set-Content -LiteralPath $FailureLog -Value $Lines -Encoding UTF8 } catch {}
}

try {
    Set-Location $Root
    New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
    if ($Root.StartsWith('\\')) { throw 'ARIADNE uses SQLite WAL mode and must run from a local Windows drive, not a UNC/network share.' }

    $Existing=Find-ExistingAriadne $PreferredPort
    if ($Existing) {
        $ExistingUrl="http://127.0.0.1:$($Existing.Port)/"
        Write-Host "ARIADNE is already running from this repository at $ExistingUrl" -ForegroundColor Green
        if (-not $VerifyOnly -and -not $NoBrowser) { Start-Process $ExistingUrl }
        exit 0
    }

    Write-Step 'Selecting a clean 64-bit CPython 3.13 or 3.11 installation'
    $Base=Select-BasePython
    Write-Host "Using CPython $($Base.Version): $($Base.Executable)"

    if ((Test-Path -LiteralPath $Venv) -and -not (Test-Venv $Base)) { Remove-IncompatibleVenv }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        Write-Step 'Creating the isolated .venv'
        $CreateArgs=@($Base.Prefix)+@('-I','-m','venv',$Venv)
        & $Base.Command @CreateArgs
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $VenvPython)) { throw 'Virtual-environment creation failed.' }
    }

    Clear-ContaminatingEnvironment

    Write-Step 'Checking pip inside the isolated environment'
    & $VenvPython -I -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        & $VenvPython -I -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed inside .venv.' }
    }

    if (-not (Test-Path -LiteralPath $Requirements)) { throw 'requirements.txt is missing from the repository.' }

    Write-Step 'Installing project requirements with outside pip configuration disabled'
    & $VenvPython -I -m pip install --disable-pip-version-check --no-input --index-url https://pypi.org/simple -r $Requirements
    if ($LASTEXITCODE -ne 0) { throw 'Requirement installation failed.' }

    Write-Step 'Running preflight, SQLite feature checks, writer-lock check, and safe database backup'
    & $VenvPython -I (Join-Path $Root 'scripts\launcher_preflight.py') --backup
    if ($LASTEXITCODE -ne 0) { throw 'ARIADNE preflight failed.' }

    Write-Step 'Compiling Python sources'
    & $VenvPython -I -m compileall -q (Join-Path $Root 'ariadne.py') (Join-Path $Root 'warden.py') (Join-Path $Root 'ariadne_core') (Join-Path $Root 'scripts')
    if ($LASTEXITCODE -ne 0) { throw 'Python compilation check failed.' }

    Write-Step 'Running the regression suite with resource-warning visibility'
    & $VenvPython -I -W 'default::ResourceWarning' -m unittest discover -s (Join-Path $Root 'tests') -v
    if ($LASTEXITCODE -ne 0) { throw 'ARIADNE regression tests failed.' }

    Write-Step 'Initializing/migrating and verifying the ARIADNE ledger'
    & $VenvPython -I (Join-Path $Root 'warden.py') verify
    if ($LASTEXITCODE -ne 0) { throw 'ARIADNE ledger verification failed.' }

    $Port=Get-OpenPort $PreferredPort
    $Url="http://127.0.0.1:$Port/"
    try { Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue } catch {}

    Write-Step "Starting ARIADNE on $Url"
    $ServerArgs=@('-I','warden.py','serve','--port',"$Port",'--interval','10','--stop-file',$StopRelative)
    $Server=Start-Process -FilePath $VenvPython -ArgumentList $ServerArgs -WorkingDirectory $Root -NoNewWindow -PassThru
    $Url=Wait-ForHealth $Server $Port

    if ($VerifyOnly) {
        Write-Step 'Stopping the smoke-test server cleanly'
        Stop-AriadneServer
        $Server.Refresh()
        if (-not $Server.HasExited) { throw 'Smoke-test server did not stop cleanly.' }
        Write-Host ""
        Write-Host 'Windows one-click bootstrap verification passed.' -ForegroundColor Green
        exit 0
    }

    $Success=@{service='ARIADNE';started_utc=[DateTime]::UtcNow.ToString('o');python=$Base.Version;python_executable=$Base.Executable;venv=$Venv;port=$Port;url=$Url;pid=$Server.Id} | ConvertTo-Json
    Set-Content -LiteralPath $SuccessLog -Value $Success -Encoding UTF8
    if (-not $NoBrowser) { Start-Process $Url }

    Write-Host ""
    Write-Host 'ARIADNE is running and its Warden worker is active.' -ForegroundColor Green
    Write-Host 'Keep this window open. Press Ctrl+C to stop ARIADNE cleanly.'
    try { Wait-Process -Id $Server.Id } finally { Stop-AriadneServer }

    $Server.Refresh()
    if ($Server.ExitCode -ne 0) { throw "ARIADNE exited with code $($Server.ExitCode)." }
}
catch {
    try { Stop-AriadneServer } catch {}
    Write-Failure $_
    Write-Host ""
    Write-Host 'STARTUP FAILED' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host 'A readable diagnostic was saved to:'
    Write-Host "  $FailureLog"
    Write-Host ""
    Write-Host 'No global Python, CUDA, NVIDIA, Conda, or Anaconda installation was changed.'
    exit 1
}
finally {
    try { Remove-Item -LiteralPath $StopFile -Force -ErrorAction SilentlyContinue } catch {}
}