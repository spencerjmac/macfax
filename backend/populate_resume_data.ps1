# Resume Tab Data Population Script
# Disables Python app alias and runs migrations + commands

$ErrorActionPreference = "Stop"

# Change to backend directory
Set-Location "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\backend"

# Full path to Python executable
$pythonPath = "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\backend\venv\Scripts\python.exe"
$managePath = "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\backend\manage.py"

Write-Host "="*80
Write-Host "Resume Tab Data Population"
Write-Host "="*80
Write-Host ""

# 1. Apply migration for game_value field
Write-Host "Step 1: Applying game_value migration..."
try {
    $proc = Start-Process -FilePath $pythonPath -ArgumentList @($managePath, "migrate") -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -eq 0) {
        Write-Host "✓ Migration applied successfully`n" -ForegroundColor Green
    } else {
        Write-Host "✗ Migration failed with exit code: $($proc.ExitCode)`n" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "✗ Migration error: $_`n" -ForegroundColor Red
    exit 1
}

# 2. Compute game_value for all games
Write-Host "Step 2: Computing game_value for all games..."
Write-Host "(This may take 2-3 minutes for all games)`n"
try {
    $proc = Start-Process -FilePath $pythonPath -ArgumentList @($managePath, "compute_game_value", "--season", "2026") -NoNewWindow -Wait -PassThru
    if ($proc.ExitCode -eq 0) {
        Write-Host "`n✓ Game values computed successfully" -ForegroundColor Green
    } else {
        Write-Host "`n✗ Game value computation failed with exit code: $($proc.ExitCode)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "`n✗ Game value computation error: $_" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "="*80
Write-Host "✓ All Resume Tab data populated successfully!" -ForegroundColor Green
Write-Host "="*80
Write-Host ""
Write-Host "You can now access the Resume tab with:"
Write-Host "  • SOR ranks (already computed)"
Write-Host "  • NET ranks (using AdjEM as proxy)"
Write-Host "  • Game values for all games"
Write-Host "  • Quadrant records (Q1-Q4)"
Write-Host "  • Best wins and worst losses tables"
Write-Host ""
