@echo off
setlocal EnableExtensions EnableDelayedExpansion
title TimeSheet Agent - Install
:: ============================================================
:: INSTALADOR: copia app\ a %LOCALAPPDATA%\TimeSheetAgent\app (oculto),
:: crea los accesos directos (Escritorio + Menu Inicio), registra la app
:: en "Agregar o quitar programas" y la abre (la primera vez instala
:: Python, Ollama y el modelo). Sin permisos de administrador.
:: ============================================================
set "SRC=%~dp0app"
set "TSA_HOME=%LOCALAPPDATA%\TimeSheetAgent"
set "APP_DIR=%TSA_HOME%\app"
set "LAUNCHER=%APP_DIR%\TimeSheet_Agent.bat"
set "ICON=%APP_DIR%\ui\icon.ico"
set "UNINSTALL_KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\TimeSheetAgent"

echo ============================================
echo   TimeSheet Agent - Install
echo ============================================
echo.

if not exist "%SRC%\app.py" (
    echo ERROR: the "app" folder was not found next to install.bat.
    echo Extract the whole ZIP first ^(right click ^> Extract All^), then run install.bat from the extracted folder.
    echo.
    pause
    exit /b 1
)

:: Version: el ZIP de un release se descomprime como TimeSheet_Agent-<version>
for %%F in ("%~dp0.") do set "FOLDER=%%~nxF"
set "VERSION=local"
echo %FOLDER%| findstr /r /i /c:"^TimeSheet_Agent-[0-9v]" >nul && set "VERSION=!FOLDER:TimeSheet_Agent-=!"

echo [1/4] Copying the application...
if not exist "%TSA_HOME%" mkdir "%TSA_HOME%"
robocopy "%SRC%" "%APP_DIR%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo ERROR: could not copy the files. If TimeSheet Agent is open, close it and run install.bat again.
    echo.
    pause
    exit /b 1
)
>"%TSA_HOME%\version.txt" <nul set /p "=!VERSION!"
echo      Installed in %APP_DIR%

echo [2/4] Creating shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = New-Object -ComObject WScript.Shell;" ^
  "$dirs = @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'));" ^
  "foreach ($d in $dirs) { $l = $s.CreateShortcut((Join-Path $d 'TimeSheet Agent.lnk'));" ^
  "  $l.TargetPath = $env:LAUNCHER; $l.WorkingDirectory = $env:TSA_HOME; $l.IconLocation = $env:ICON;" ^
  "  $l.Description = 'TimeSheet Agent - hours for Workday and N4W'; $l.Save() }"
if errorlevel 1 (
    echo      WARNING: could not create the shortcuts. You can open the app with %LAUNCHER%
) else (
    echo      Desktop and Start menu: "TimeSheet Agent"
)

echo [3/4] Registering in "Installed apps"...
reg add "%UNINSTALL_KEY%" /v DisplayName /d "TimeSheet Agent" /f >nul
reg add "%UNINSTALL_KEY%" /v DisplayVersion /d "!VERSION:v=!" /f >nul
reg add "%UNINSTALL_KEY%" /v Publisher /d "N4W Facility" /f >nul
reg add "%UNINSTALL_KEY%" /v DisplayIcon /d "%ICON%" /f >nul
reg add "%UNINSTALL_KEY%" /v InstallLocation /d "%TSA_HOME%" /f >nul
reg add "%UNINSTALL_KEY%" /v UninstallString /d "\"%APP_DIR%\uninstall.bat\"" /f >nul
reg add "%UNINSTALL_KEY%" /v NoModify /t REG_DWORD /d 1 /f >nul
reg add "%UNINSTALL_KEY%" /v NoRepair /t REG_DWORD /d 1 /f >nul
echo      Done.

echo [4/4] Opening TimeSheet Agent (the first time it sets up Python, Ollama and the model)...
echo.
echo Installation complete. You can delete the downloaded folder.
echo From now on open the app from the Desktop or the Start menu: "TimeSheet Agent".
echo.
start "TimeSheet Agent" "%LAUNCHER%"
pause
endlocal
exit /b 0
