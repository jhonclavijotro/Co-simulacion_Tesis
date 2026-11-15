$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

Write-Host "===================================================" -ForegroundColor Cyan
Write-Host " Iniciando Centro de Mando / Dashboard Web MAS" -ForegroundColor Cyan
Write-Host "===================================================" -ForegroundColor Cyan

Start-Process "http://localhost:8000/web_dashboard.html"

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$DashboardScript = Join-Path $ProjectDir "GUI\rpi_dashboard_service.py"

if (Test-Path $VenvPython) {
    Write-Host "Usando entorno virtual: $VenvPython" -ForegroundColor Green
    & $VenvPython $DashboardScript --standalone
} else {
    Write-Host "Usando Python en PATH..." -ForegroundColor Yellow
    python $DashboardScript --standalone
}
