# ============================================================================
# CBB Analytics Dashboard - Automated Update Script
# ============================================================================
# This script runs the complete data pipeline to update all statistics
# It includes error handling, logging, and email notifications (optional)
#
# Usage:
#   .\update_dashboard.ps1
#   .\update_dashboard.ps1 -SkipIngest  # Skip game ingestion, only recompute
#
# Schedule with Windows Task Scheduler for automatic updates
# ============================================================================

param(
    [switch]$SkipIngest = $false,
    [int]$Season = 2026
)

# Configuration
$ProjectRoot = "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard"
$PythonExe = "$ProjectRoot\.venv\Scripts\python.exe"
$BackendDir = "$ProjectRoot\backend"
$LogDir = "$ProjectRoot\logs"
$LogFile = "$LogDir\update_$(Get-Date -Format 'yyyyMMdd_HHmmss').log"

# Create logs directory if it doesn't exist
if (!(Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
}

# Function to write log messages
function Write-Log {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )
    
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $LogMessage = "[$Timestamp] [$Level] $Message"
    
    # Write to console
    switch ($Level) {
        "ERROR" { Write-Host $LogMessage -ForegroundColor Red }
        "SUCCESS" { Write-Host $LogMessage -ForegroundColor Green }
        "WARNING" { Write-Host $LogMessage -ForegroundColor Yellow }
        default { Write-Host $LogMessage }
    }
    
    # Write to log file
    Add-Content -Path $LogFile -Value $LogMessage
}

# Start update
Write-Log "============================================================================" "INFO"
Write-Log "CBB Analytics Dashboard - Automated Update Starting" "INFO"
Write-Log "============================================================================" "INFO"
Write-Log "Season: $Season" "INFO"
Write-Log "Skip Ingest: $SkipIngest" "INFO"
Write-Log "Log File: $LogFile" "INFO"
Write-Log "============================================================================" "INFO"
Write-Log "" "INFO"

try {
    # Change to backend directory
    Set-Location $BackendDir
    Write-Log "Changed to backend directory: $BackendDir" "INFO"
    
    # Build command
    $CommandArgs = @(
        "manage.py",
        "update_all",
        "--season", $Season
    )
    
    if ($SkipIngest) {
        $CommandArgs += "--skip-ingest"
    }
    
    Write-Log "Executing: python $($CommandArgs -join ' ')" "INFO"
    Write-Log "" "INFO"
    
    # Run the update command
    $StartTime = Get-Date
    
    # Capture both stdout and stderr
    $ProcessInfo = New-Object System.Diagnostics.ProcessStartInfo
    $ProcessInfo.FileName = $PythonExe
    $ProcessInfo.Arguments = $CommandArgs -join " "
    $ProcessInfo.RedirectStandardError = $true
    $ProcessInfo.RedirectStandardOutput = $true
    $ProcessInfo.UseShellExecute = $false
    $ProcessInfo.CreateNoWindow = $true
    $ProcessInfo.WorkingDirectory = $BackendDir
    
    $Process = New-Object System.Diagnostics.Process
    $Process.StartInfo = $ProcessInfo
    
    # Event handlers for output
    $stdout = New-Object System.Text.StringBuilder
    $stderr = New-Object System.Text.StringBuilder
    
    $OutputHandler = {
        if ($EventArgs.Data) {
            $stdout.AppendLine($EventArgs.Data)
            Write-Host $EventArgs.Data
            Add-Content -Path $LogFile -Value $EventArgs.Data
        }
    }
    
    $ErrorHandler = {
        if ($EventArgs.Data) {
            $stderr.AppendLine($EventArgs.Data)
            Write-Host $EventArgs.Data -ForegroundColor Red
            Add-Content -Path $LogFile -Value "ERROR: $($EventArgs.Data)"
        }
    }
    
    Register-ObjectEvent -InputObject $Process `
        -EventName OutputDataReceived -Action $OutputHandler | Out-Null
    Register-ObjectEvent -InputObject $Process `
        -EventName ErrorDataReceived -Action $ErrorHandler | Out-Null
    
    # Start process
    $Process.Start() | Out-Null
    $Process.BeginOutputReadLine()
    $Process.BeginErrorReadLine()
    $Process.WaitForExit()
    
    $EndTime = Get-Date
    $Duration = ($EndTime - $StartTime).TotalSeconds
    $ExitCode = $Process.ExitCode
    
    # Clean up event handlers
    Get-EventSubscriber | Where-Object { $_.SourceObject -eq $Process } | Unregister-Event
    
    Write-Log "" "INFO"
    Write-Log "============================================================================" "INFO"
    
    if ($ExitCode -eq 0) {
        Write-Log "✅ UPDATE COMPLETED SUCCESSFULLY" "SUCCESS"
        Write-Log "Duration: $([math]::Round($Duration, 1)) seconds ($([math]::Round($Duration/60, 1)) minutes)" "SUCCESS"
        Write-Log "Exit Code: $ExitCode" "SUCCESS"
        Write-Log "" "SUCCESS"
        Write-Log "📊 All data has been updated!" "SUCCESS"
        Write-Log "🌐 Website will show latest statistics" "SUCCESS"
        $Success = $true
    } else {
        Write-Log "⚠️  UPDATE COMPLETED WITH ERRORS" "ERROR"
        Write-Log "Duration: $([math]::Round($Duration, 1)) seconds" "ERROR"
        Write-Log "Exit Code: $ExitCode" "ERROR"
        Write-Log "" "ERROR"
        Write-Log "Check the log file for details: $LogFile" "ERROR"
        $Success = $false
    }
    
} catch {
    Write-Log "" "ERROR"
    Write-Log "============================================================================" "ERROR"
    Write-Log "❌ CRITICAL ERROR OCCURRED" "ERROR"
    Write-Log "Error: $($_.Exception.Message)" "ERROR"
    Write-Log "Stack Trace: $($_.ScriptStackTrace)" "ERROR"
    $Success = $false
}

Write-Log "============================================================================" "INFO"
Write-Log "" "INFO"

# Optional: Send email notification (configure SMTP settings)
# Uncomment and configure if you want email alerts
<#
if (!$Success) {
    $EmailParams = @{
        From = "dashboard@yourdomain.com"
        To = "your-email@example.com"
        Subject = "⚠️ CBB Dashboard Update Failed"
        Body = "The automated update failed. Check log: $LogFile"
        SmtpServer = "smtp.gmail.com"
        Port = 587
        UseSsl = $true
        Credential = (Get-Credential)
    }
    Send-MailMessage @EmailParams
}
#>

# Keep a maximum of 30 days of logs
Write-Log "Cleaning up old log files (older than 30 days)..." "INFO"
Get-ChildItem -Path $LogDir -Filter "update_*.log" | 
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } |
    Remove-Item -Force
Write-Log "Log cleanup complete" "INFO"

Write-Log "" "INFO"
Write-Log "Script completed. Log saved to: $LogFile" "INFO"

# Return exit code
if ($Success) {
    exit 0
} else {
    exit 1
}
