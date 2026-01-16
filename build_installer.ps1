$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$issPath = Join-Path $root "EazyTestinstall.iss"
if (-not (Test-Path $issPath)) {
    throw "Missing EazyTestinstall.iss"
}

$exePath = Join-Path $root "dist\\EazyTest.exe"
if (-not (Test-Path $exePath)) {
    throw "Missing dist\\EazyTest.exe. Run build_exe.ps1 first."
}

$iscc = (Get-Command ISCC -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $default = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\\ISCC.exe"
    if (Test-Path $default) {
        $iscc = $default
    }
}
if (-not $iscc) {
    $custom = "D:\\works\\Inno Setup 6\\ISCC.exe"
    if (Test-Path $custom) {
        $iscc = $custom
    }
}
if (-not $iscc) {
    throw "Inno Setup not found. Install Inno Setup 6 and try again."
}

Write-Host "Running: $iscc $issPath"
& $iscc $issPath
