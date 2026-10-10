@echo off
setlocal EnableExtensions
title TimeSheet Agent - Uninstall
:: ============================================================
:: DESINSTALADOR ("Agregar o quitar programas" o doble clic).
:: Borra el codigo, Python (mamba) y los accesos directos. El historial y
:: los ajustes se borran solo si el usuario lo pide; Documents\TimeSheetAgent
:: (CSV y reportes) y Ollama no se tocan.
:: ============================================================
set "TSA_HOME=%LOCALAPPDATA%\TimeSheetAgent"
set "UNINSTALL_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\TimeSheetAgent"

:: corre desde TEMP: este archivo esta dentro de la carpeta que se borra
if /i not "%~1"=="--from-temp" (
    copy /y "%~f0" "%TEMP%\TimeSheetAgent_uninstall.bat" >nul
    "%TEMP%\TimeSheetAgent_uninstall.bat" --from-temp
)
cd /d "%TEMP%"

echo ============================================
echo   TimeSheet Agent - Uninstall
echo ============================================
echo.
choice /c YN /m "Uninstall TimeSheet Agent"
if errorlevel 2 goto :END

set "WIPE_DATA=0"
echo.
echo Your hours history and settings are kept, so a reinstall picks up where you left off.
choice /c YN /m "Delete them too"
if not errorlevel 2 set "WIPE_DATA=1"

echo.
echo Closing Tributary on the desktop...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'pythonw.exe' -and $_.CommandLine -like '*companion.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo Removing shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  Remove-Item -LiteralPath (Join-Path $d 'TimeSheet Agent.lnk') -Force -ErrorAction SilentlyContinue }" ^
  "; Remove-Item -LiteralPath (Join-Path ([Environment]::GetFolderPath('Startup')) 'TimeSheet Agent - Tributary.lnk') -Force -ErrorAction SilentlyContinue"

echo Removing the application and its Python environment...
rmdir /s /q "%TSA_HOME%\app" 2>nul
if exist "%TSA_HOME%\app" (
    echo.
    echo ERROR: TimeSheet Agent is open. Close it and run the uninstall again.
    echo.
    pause
    goto :END
)
rmdir /s /q "%TSA_HOME%\app.old" 2>nul
rmdir /s /q "%TSA_HOME%\mamba" 2>nul
del /f /q "%TSA_HOME%\micromamba.exe" "%TSA_HOME%\version.txt" 2>nul

if "%WIPE_DATA%"=="1" (
    echo Removing history and settings...
    rmdir /s /q "%TSA_HOME%" 2>nul
)
reg delete "%UNINSTALL_KEY%" /f >nul 2>&1

echo.
echo TimeSheet Agent was uninstalled.
echo Your CSV files and reports in Documents\TimeSheetAgent were not touched.
echo Ollama is a separate program: remove it from "Installed apps" if you no longer need it.
echo.
pause

:END
endlocal
(goto) 2>nul & del "%~f0"
