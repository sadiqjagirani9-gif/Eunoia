@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if errorlevel 1 (
  echo Python launcher was not found. Install Python 3.11 and try again.
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js was not found. Install Node.js 20 or later and try again.
  pause
  exit /b 1
)
if not exist .venv\Scripts\python.exe py -3.11 -m venv .venv
if not exist .venv\Scripts\python.exe (
  echo Python 3.11 is required to create the virtual environment.
  pause
  exit /b 1
)
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
if not exist frontend\node_modules call npm --prefix frontend install
if errorlevel 1 (
  pause
  exit /b 1
)

start "Eunoia API" powershell -NoExit -Command "Set-Location '%~dp0backend'; & '..\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Eunoia UI" powershell -NoExit -Command "Set-Location '%~dp0frontend'; npm run dev"
echo Waiting for the local website to start...
powershell -NoProfile -Command "$ready=$false; for($i=0;$i -lt 60;$i++){try{$r=Invoke-WebRequest -UseBasicParsing http://127.0.0.1:6081 -TimeoutSec 2;if($r.StatusCode -eq 200){$ready=$true;break}}catch{};Start-Sleep -Seconds 1};if($ready){Start-Process 'http://127.0.0.1:6081'}else{Write-Host 'Eunoia UI did not start. Check the Eunoia UI terminal for errors.';exit 1}"
if errorlevel 1 pause
endlocal
