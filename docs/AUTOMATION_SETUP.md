# 🤖 Automated Updates Setup Guide

Complete guide to set up automatic data updates for the CBB Analytics Dashboard.

## 📋 Overview

This automation system runs the complete data pipeline automatically on a schedule:

1. **Ingest game logs** from NCAA API
2. **Compute statistics** (raw metrics, adjusted ratings, four factors)
3. **Fetch NET rankings** from NCAA.com
4. **Compute resume metrics** (SOR, SOS, game values)
5. **Update all website data** automatically

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Test the Update Command

First, verify the automation works manually:

```powershell
cd "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\backend"
& "..\\.venv\Scripts\python.exe" manage.py update_all --season 2026
```

This will run all 8 pipeline steps in sequence. Expected time: **5-8 minutes**.

### Step 2: Test the PowerShell Script

```powershell
cd "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard"
.\update_dashboard.ps1
```

Check the log file in `logs/` folder to verify it worked correctly.

### Step 3: Set Up Task Scheduler

Follow the detailed instructions below to schedule automatic updates.

---

## 📅 Windows Task Scheduler Setup

### Option A: Quick Setup (Recommended for Daily Updates)

1. **Open Task Scheduler**
   - Press `Windows + R`
   - Type: `taskschd.msc`
   - Press Enter

2. **Create Basic Task**
   - Click "Create Basic Task..." in right panel
   - Name: `CBB Dashboard Update`
   - Description: `Automated daily update for CBB Analytics Dashboard`
   - Click "Next"

3. **Set Trigger**
   - Select "Daily"
   - Click "Next"
   - Start: Today's date
   - Time: `06:00 AM` (after overnight games finish)
   - Recur every: `1` days
   - Click "Next"

4. **Set Action**
   - Select "Start a program"
   - Click "Next"
   - Program/script: `powershell.exe`
   - Add arguments: `-ExecutionPolicy Bypass -File "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\update_dashboard.ps1"`
   - Click "Next"

5. **Finish**
   - Check "Open Properties dialog when I click Finish"
   - Click "Finish"

6. **Configure Additional Settings** (in Properties dialog)
   - **General tab:**
     - ☑ "Run whether user is logged on or not"
     - ☑ "Run with highest privileges"
     - Configure for: Windows 10
   
   - **Conditions tab:**
     - ☐ Uncheck "Start the task only if the computer is on AC power"
     - ☑ "Wake the computer to run this task"
   
   - **Settings tab:**
     - ☑ "Allow task to be run on demand"
     - ☑ "Run task as soon as possible after a scheduled start is missed"
     - If running: "Do not start a new instance"

7. **Save**
   - Click "OK"
   - Enter your Windows password when prompted

---

### Option B: Multiple Updates Per Day (For More Frequent Updates)

If you want to update multiple times per day (e.g., every 6 hours):

1. Follow Option A steps 1-4
2. In Properties dialog, go to **Triggers** tab
3. Click "New..." to add additional triggers:
   - **6 AM**: After overnight games
   - **12 PM**: Midday update
   - **6 PM**: Before evening games
   - **12 AM**: After evening games

4. Configure each trigger as "Daily" at the specific time
5. Save and test

---

## ✅ Verify It's Working

### Test the Scheduled Task

1. **Manual Test:**
   - Open Task Scheduler
   - Find "CBB Dashboard Update"
   - Right-click → "Run"
   - Check "Last Run Result" (should be "The operation completed successfully (0x0)")

2. **Check Logs:**
   ```powershell
   cd "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard"
   Get-ChildItem logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
   Get-Content (Get-ChildItem logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
   ```

3. **Monitor Execution:**
   - Check Task Scheduler History tab
   - Review log files in `logs/` folder
   - Verify website shows updated data

---

## 🎯 Update Frequencies

Choose the update frequency that works for you:

| Frequency | Trigger Schedule | Best For | Data Freshness |
|-----------|-----------------|----------|----------------|
| **1x daily** | 6:00 AM | Testing, low traffic | Within 24 hours |
| **2x daily** | 6:00 AM, 6:00 PM | Standard use | Within 12 hours |
| **4x daily** | 6:00 AM, 12:00 PM, 6:00 PM, 12:00 AM | Active use | Within 6 hours |
| **Every 6 hours** | 12:00 AM, 6:00 AM, 12:00 PM, 6:00 PM | High traffic | Within 6 hours |
| **Every hour** | Every hour | Production | Within 1 hour |

**Recommended:** Start with **1x daily at 6 AM**. Increase frequency later as needed.

---

## 🔧 Configuration Options

### Skip Game Ingestion (Faster Updates)

If you only want to recompute statistics without fetching new games:

**PowerShell Script:**
```powershell
.\update_dashboard.ps1 -SkipIngest
```

**Task Scheduler Arguments:**
```
-ExecutionPolicy Bypass -File "C:\Users\spenc\OneDrive\Workspace\CBB Analytical Dashboard\update_dashboard.ps1" -SkipIngest
```

This is useful for:
- Testing
- Recomputing after data fixes
- When you know no new games have been played

### Adjust Computation Parameters

Edit `update_dashboard.ps1` to customize:

```powershell
# Line 75-80 (approximately)
$CommandArgs = @(
    "manage.py",
    "update_all",
    "--season", $Season,
    "--iterations", 10,          # Change iterations for adjusted ratings
    "--sor-trials", 10000        # Change Monte Carlo trials for SOR
)
```

---

## 📊 Monitoring & Logs

### Log Files

- **Location:** `logs/update_YYYYMMDD_HHMMSS.log`
- **Retention:** Automatically cleaned after 30 days
- **Contents:** Complete execution log with timestamps

**View Latest Log:**
```powershell
$latest = Get-ChildItem logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $latest.FullName
```

**Check for Errors:**
```powershell
$latest = Get-ChildItem logs | Sort-Object LastWriteTime -Descending | Select-Object -First 1
Get-Content $latest.FullName | Select-String -Pattern "ERROR|FAIL"
```

### Email Notifications (Optional)

To receive email alerts on failures, edit `update_dashboard.ps1` and uncomment lines 165-176:

```powershell
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
```

Configure your SMTP settings as appropriate.

---

## 🐛 Troubleshooting

### Task Doesn't Run

**Problem:** Task shows as "Ready" but never runs
- **Solution:** Check triggers are enabled
- **Solution:** Verify "Run whether user is logged on or not" is checked
- **Solution:** Make sure computer is on at scheduled time

### Task Fails with Error

**Problem:** Last Run Result shows error code
- **Solution:** Check log file for details
- **Solution:** Verify Python virtual environment is activated
- **Solution:** Test script manually: `.\update_dashboard.ps1`

### Script Permission Errors

**Problem:** "Execution of scripts is disabled on this system"
- **Solution:** Run PowerShell as Administrator:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```

### Computer Sleeping During Update

**Problem:** Update doesn't run because computer is asleep
- **Solution:** In Task Scheduler, Conditions tab:
  - ☑ "Wake the computer to run this task"
- **Solution:** Adjust Windows power settings to prevent sleep during task times

### Long Execution Time

**Problem:** Update takes too long to complete
- **Solution:** Reduce SOR trials: `--sor-trials 5000`
- **Solution:** Reduce iterations: `--iterations 5`
- **Solution:** Use `--skip-ingest` when no new games available

---

## 🚀 Advanced: Production Deployment

For 24/7 automated updates on a production server (not dependent on your PC):

### Recommended Services

1. **Railway.app** (Easiest)
   - Deploy Django backend to Railway
   - Add cron job in railway.toml:
     ```toml
     [[cron]]
     schedule = "0 6 * * *"
     command = "python manage.py update_all --season 2026"
     ```

2. **Render.com**
   - Deploy backend as web service
   - Add cron job in render.yaml:
     ```yaml
     - type: cron
       name: update-dashboard
       schedule: "0 6 * * *"
       command: python manage.py update_all --season 2026
     ```

3. **DigitalOcean/AWS EC2**
   - Deploy to VPS
   - Set up cron job:
     ```bash
     crontab -e
     0 6 * * * /path/to/venv/bin/python /path/to/manage.py update_all --season 2026
     ```

See [DEPLOYMENT.md](DEPLOYMENT.md) for full production deployment guide.

---

## 📝 Summary

**What You Did:**
1. ✅ Created `update_all` Django command
2. ✅ Created `update_dashboard.ps1` PowerShell script
3. ✅ Set up Windows Task Scheduler

**What Happens Now:**
- Dashboard updates automatically on schedule
- All statistics stay current
- Logs track every update
- Website always shows latest data

**Next Steps:**
- Monitor first few automated runs
- Adjust frequency as needed
- Consider production deployment for 24/7 operation

---

## 🆘 Need Help?

- Check log files: `logs/`
- Test manually: `.\update_dashboard.ps1`
- View Task Scheduler history
- Review [README.md](../README.md) for pipeline details

Happy automating! 🎉
