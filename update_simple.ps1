# Simple Update Script for CBB Dashboard
# Just runs the Django update_all command

$ErrorActionPreference = "Continue"
$ProjectRoot = "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard"
$LogFile = "$ProjectRoot\last_update.log"

# Start logging
$Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
"===========================================
" | Out-File $LogFile
"CBB Dashboard Update - $Timestamp" | Out-File $LogFile -Append
"===========================================
" | Out-File $LogFile -Append

# Change to backend directory
Set-Location "$ProjectRoot\backend"

# Run the Django update command
Write-Host "Running update_all command..." -ForegroundColor Cyan
& "$ProjectRoot\.venv\Scripts\python.exe" manage.py update_all --season 2026 *>&1 | Tee-Object -FilePath $LogFile -Append

# Check if it succeeded
if ($LASTEXITCODE -eq 0) {
    Write-Host "Update completed successfully!" -ForegroundColor Green
    "
Success! Update completed at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File $LogFile -Append
    exit 0
} else {
    Write-Host "Update failed with exit code: $LASTEXITCODE" -ForegroundColor Red
    "
Failed with exit code: $LASTEXITCODE" | Out-File $LogFile -Append
    exit $LASTEXITCODE
}
