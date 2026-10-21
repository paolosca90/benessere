@echo off
setlocal
cd /d "%~dp0"
title Benessere - Avvio

where python >nul 2>nul
if errorlevel 1 (
  echo [ERRORE] Python non trovato. Installa Python 3.12 o aggiungilo al PATH.
  pause
  exit /b 1
)

python -c "import streamlit; import mcp" >nul 2>nul
if errorlevel 1 (
  echo [ERRORE] Dipendenze mancanti. Esegui: python -m pip install -r requirements.txt
  pause
  exit /b 1
)

powershell.exe -NoProfile -Command "try { $r = Invoke-WebRequest 'http://127.0.0.1:8501/_stcore/health' -UseBasicParsing -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 }; exit 1 } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo [AVVIO] Dashboard Benessere (porta 8501)...
  start "Benessere - Dashboard" /MIN cmd /k "cd /d ""%~dp0"" && python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501"
) else (
  echo [OK] Dashboard gia' attiva su http://127.0.0.1:8501
)

powershell.exe -NoProfile -Command "if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { exit 0 } else { exit 1 }" >nul 2>nul
if errorlevel 1 (
  echo [AVVIO] Server MCP Benessere solo in locale (porta 8000)...
  start "Benessere - MCP" /MIN cmd /k "cd /d ""%~dp0"" && python mcp_server.py --http 8000"
) else (
  echo [INFO] Porta 8000 gia' occupata: verifica che sia il server MCP Benessere.
)

echo.
echo Dashboard: http://127.0.0.1:8501
echo MCP locale: http://127.0.0.1:8000/mcp
echo NOTA: ChatGPT non puo' collegarsi direttamente a localhost.
echo Per collegarlo serve un tunnel sicuro: consulta docs\07-mcp-chatgpt.md.
start "" "http://127.0.0.1:8501"
echo.
pause
