@echo off
setlocal
cd /d "%~dp0"
title Benessere - Sync Android

echo ======================================================
echo  BENESSERE - SYNC ANDROID PC (PORTA 8766)
echo ======================================================
echo.
echo IMPORTANTE: HTTP senza cifratura, consentito SOLO su
echo Wi-Fi privata fidata. NON aprire 8766 su router/Internet.
echo Premi CTRL+C per fermare il server.
echo.
echo Token: viene generato al primo avvio e mostrato qui.
echo NON inviarlo su chat, GitHub o screenshot.
echo.
echo Indirizzi IPv4 del PC:
ipconfig | findstr /C:"IPv4"
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo ERRORE: Python non trovato.
  pause
  exit /b 1
)
python sync_server.py --lan
echo.
echo Server arrestato.
pause
