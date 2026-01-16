$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    python -m pip install --upgrade pyinstaller
}

$docx = Get-ChildItem -Path "src" -Filter *.docx | Select-Object -First 1
if (-not $docx) {
    throw "Missing .docx file in src"
}

$dataArgs = @(
    "assets;assets",
    "$($docx.FullName);src",
    "src/dbcase.xlsx;src",
    "src/chatgptcase.xlsx;src",
    "src/requesttool/app/assets/templates/report.html;src/requesttool/app/assets/templates"
)

$addData = $dataArgs | ForEach-Object { "--add-data `"$($_)`"" }
$cmd = "pyinstaller --noconsole --onefile --name `"EazyTest`" --icon assets\\lightning.ico --paths `"src`" --collect-submodules requesttool $($addData -join ' ') main.py"

Write-Host "Running: $cmd"
Invoke-Expression $cmd
