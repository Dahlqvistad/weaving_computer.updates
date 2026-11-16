#Requires -Version 5.1

[CmdletBinding()]
param(
    [string]$Version,
    [int]$Sequence,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Refresh-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machinePath;$userPath"
}

function Install-Command {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [Parameter(Mandatory = $true)]
        [string]$PackageId
    )

    if (Get-Command $Command -ErrorAction SilentlyContinue) {
        return
    }
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "'$Command' is missing and winget is unavailable. Install $PackageId first."
    }

    Write-Host "Installing $PackageId..."
    winget install --exact --id $PackageId --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install $PackageId (exit $LASTEXITCODE)."
    }
    Refresh-ProcessPath
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "$PackageId was installed, but '$Command' is not available in PATH. Open a new PowerShell window and rerun this command."
    }
}

Install-Command -Command "git.exe" -PackageId "Git.Git"
Install-Command -Command "gh.exe" -PackageId "GitHub.cli"
Install-Command -Command "dotnet.exe" -PackageId "Microsoft.DotNet.SDK.8"

$dotnet8 = & dotnet.exe --list-sdks | Select-String -Pattern "^8\."
if (-not $dotnet8) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "The .NET 8 SDK is required and winget is unavailable. Install .NET 8 first."
    }
    Write-Host "Installing the .NET 8 SDK..."
    winget install --exact --id Microsoft.DotNet.SDK.8 --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install the .NET 8 SDK (exit $LASTEXITCODE)."
    }
    Refresh-ProcessPath
}

$pythonCommand = $null
$pythonPrefix = @()
if (Get-Command py.exe -ErrorAction SilentlyContinue) {
    & py.exe -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" *> $null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "py.exe"
        $pythonPrefix = @("-3.12")
    }
}
if (-not $pythonCommand -and (Get-Command python.exe -ErrorAction SilentlyContinue)) {
    & python.exe -c "import sys; assert sys.version_info[:2] == (3, 12)" *> $null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = "python.exe"
    }
}
if (-not $pythonCommand) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Python 3.12 x64 is required and winget is unavailable. Install Python 3.12 first."
    }
    Write-Host "Installing Python 3.12..."
    winget install --exact --id Python.Python.3.12 --silent `
        --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget could not install Python 3.12 (exit $LASTEXITCODE)."
    }
    Refresh-ProcessPath
    if (Get-Command py.exe -ErrorAction SilentlyContinue) {
        $pythonCommand = "py.exe"
        $pythonPrefix = @("-3.12")
    }
    elseif (Get-Command python.exe -ErrorAction SilentlyContinue) {
        $pythonCommand = "python.exe"
    }
    else {
        throw "Python was installed but is not available in PATH. Open a new PowerShell window and rerun this command."
    }
}

& $pythonCommand @pythonPrefix -c "import platform, struct; assert struct.calcsize('P') == 8 and platform.machine().lower() in {'amd64', 'x86_64'}" *> $null
if ($LASTEXITCODE -ne 0) {
    throw "The build requires 64-bit x86 Python 3.12."
}

& gh.exe auth status --hostname github.com
if ($LASTEXITCODE -ne 0) {
    Write-Host "Sign in to GitHub in the browser window..."
    & gh.exe auth login --hostname github.com --web --git-protocol https --scopes "repo"
    if ($LASTEXITCODE -ne 0) {
        throw "GitHub authentication failed."
    }
}
& gh.exe auth setup-git
if ($LASTEXITCODE -ne 0) {
    throw "GitHub CLI could not configure Git authentication."
}

& git.exe -C $PSScriptRoot pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    throw "The updates repository could not be fast-forwarded to origin/main. Commit or remove local changes, then retry."
}

$arguments = @("-m", "scripts.build_offline_windows")
if ($Version) {
    $arguments += @("--version", $Version)
}
if ($PSBoundParameters.ContainsKey("Sequence")) {
    $arguments += @("--sequence", $Sequence.ToString())
}
if ($SkipTests) {
    Write-Warning "Tests are being skipped. Use this only for an explicitly accepted emergency build."
    $arguments += "--skip-tests"
}

Push-Location $PSScriptRoot
try {
    & $pythonCommand @pythonPrefix @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "The local build failed (exit $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
