param(
    [string]$RepoPath = "C:\Users\Repair SC\ZCodeProject\revit"
)

$ErrorActionPreference = "Stop"
$originalLocation = Get-Location

try {
    Set-Location $RepoPath
    Write-Host "=== Working directory: $(Get-Location) ===" -ForegroundColor Cyan

    # 1. git fetch origin main
    Write-Host "`n[1/6] git fetch origin main" -ForegroundColor Yellow
    $output = git fetch origin main 2>&1
    Write-Host $output

    # 2. git reset --hard origin/main
    Write-Host "`n[2/6] git reset --hard origin/main" -ForegroundColor Yellow
    $output = git reset --hard origin/main 2>&1
    Write-Host $output

    # 3. git clean -fd
    Write-Host "`n[3/6] git clean -fd" -ForegroundColor Yellow
    $output = git clean -fd 2>&1
    Write-Host $output

    # 4. git status
    Write-Host "`n[4/6] git status" -ForegroundColor Yellow
    $output = git status 2>&1
    Write-Host $output

    # 5. git log --oneline -10
    Write-Host "`n[5/6] git log --oneline -10" -ForegroundColor Yellow
    $output = git log --oneline -10 2>&1
    Write-Host $output

    # 6. git diff origin/main
    Write-Host "`n[6/6] git diff origin/main" -ForegroundColor Yellow
    $output = git diff origin/main 2>&1
    Write-Host $output

    Write-Host "`n=== All commands completed ===" -ForegroundColor Green
}
catch {
    Write-Host "`nERROR: $_" -ForegroundColor Red
    exit 1
}
finally {
    Set-Location $originalLocation
}
