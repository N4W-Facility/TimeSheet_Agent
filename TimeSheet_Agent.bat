@echo off
setlocal EnableExtensions EnableDelayedExpansion
title TimeSheet Agent
cd /d "%~dp0"

echo ============================================
echo   TimeSheet Agent - Setup and launch
echo ============================================
echo.

:: ============================================
:: Variables
:: ============================================
set "APP_DIR=%~dp0"
set "TSA_HOME=%LOCALAPPDATA%\TimeSheetAgent"
set "MAMBA_EXE=%TSA_HOME%\micromamba.exe"
set "MAMBA_ROOT_PREFIX=%TSA_HOME%\mamba"
set "ENV_NAME=timesheet-agent"
set "ENV_DIR=%MAMBA_ROOT_PREFIX%\envs\%ENV_NAME%"
set "ENV_FILE=%APP_DIR%environment.yml"
set "ENV_STAMP=%ENV_DIR%\.environment.sha256"
set "MAMBA_URL=https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64"
set "OLLAMA_URL=https://ollama.com/download/OllamaSetup.exe"
set "OLLAMA_INSTALLER=%TEMP%\OllamaSetup.exe"
set "OLLAMA_DIR=%LOCALAPPDATA%\Programs\Ollama"
set "OLLAMA_EXE="
set "OLLAMA_API=http://127.0.0.1:11434/api/version"
set "MODEL=qwen3:8b"
if defined TSA_OLLAMA_MODEL set "MODEL=%TSA_OLLAMA_MODEL%"

if not exist "%TSA_HOME%" mkdir "%TSA_HOME%"

:: ============================================
:: PASO 1: Micromamba
:: ============================================
echo [1/4] Checking micromamba...
if exist "%MAMBA_EXE%" (
    echo      Found: %MAMBA_EXE%
    goto :ENV
)

echo      Downloading micromamba...
curl.exe -L --fail -o "%MAMBA_EXE%" "%MAMBA_URL%"
if not exist "%MAMBA_EXE%" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri '%MAMBA_URL%' -OutFile '%MAMBA_EXE%'"
)
if not exist "%MAMBA_EXE%" (
    set "ERR=Could not download micromamba. Check your internet connection."
    goto :FAIL
)
echo      micromamba installed.

:: ============================================
:: PASO 2: Ambiente (se recrea si environment.yml cambia)
:: ============================================
:ENV
echo.
echo [2/4] Checking Python environment...

set "ENV_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -Algorithm SHA256 -LiteralPath '%ENV_FILE%').Hash"`) do set "ENV_HASH=%%H"
set "OLD_HASH="
if exist "%ENV_STAMP%" set /p OLD_HASH=<"%ENV_STAMP%"

if exist "%ENV_DIR%\python.exe" (
    if "!ENV_HASH!"=="!OLD_HASH!" (
        echo      Environment up to date.
        goto :OLLAMA
    )
    echo      environment.yml changed - rebuilding environment...
    "%MAMBA_EXE%" env remove -y -r "%MAMBA_ROOT_PREFIX%" -n %ENV_NAME%
) else (
    echo      Creating environment - first time only, this can take a few minutes...
)

"%MAMBA_EXE%" create -y -r "%MAMBA_ROOT_PREFIX%" -n %ENV_NAME% -f "%ENV_FILE%"
if errorlevel 1 (
    set "ERR=Could not create the Python environment."
    goto :FAIL
)
if not exist "%ENV_DIR%\python.exe" (
    set "ERR=The Python environment was not created correctly."
    goto :FAIL
)
>"%ENV_STAMP%" echo !ENV_HASH!
echo      Environment ready.

:: ============================================
:: PASO 3: Ollama + modelo
:: ============================================
:OLLAMA
echo.
echo [3/4] Checking Ollama...

:: Servidor compartido configurado: no se instala nada localmente
if defined TSA_OLLAMA_HOST (
    echo      Using shared server %TSA_OLLAMA_HOST% - skipping local Ollama.
    goto :RUN_APP
)

where ollama >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%O in ('where ollama') do if not defined OLLAMA_EXE set "OLLAMA_EXE=%%O"
)
if not defined OLLAMA_EXE if exist "%OLLAMA_DIR%\ollama.exe" set "OLLAMA_EXE=%OLLAMA_DIR%\ollama.exe"
if defined OLLAMA_EXE (
    echo      Found: !OLLAMA_EXE!
    goto :OLLAMA_START
)

echo      Ollama not found. Downloading installer...
curl.exe -L --fail -o "%OLLAMA_INSTALLER%" "%OLLAMA_URL%"
if not exist "%OLLAMA_INSTALLER%" (
    set "ERR=Could not download Ollama. Check your internet connection."
    goto :FAIL
)
echo      Installing Ollama silently...
start /wait "" "%OLLAMA_INSTALLER%" /VERYSILENT /NORESTART /SUPPRESSMSGBOXES
del "%OLLAMA_INSTALLER%" 2>nul
if not exist "%OLLAMA_DIR%\ollama.exe" (
    set "ERR=Ollama installation failed."
    goto :FAIL
)
set "OLLAMA_EXE=%OLLAMA_DIR%\ollama.exe"
echo      Ollama installed.

:OLLAMA_START
curl.exe -s -f -o nul "%OLLAMA_API%" >nul 2>&1
if not errorlevel 1 (
    echo      Ollama service running.
    goto :MODEL
)

echo      Starting Ollama service...
for %%D in ("!OLLAMA_EXE!") do set "OLLAMA_BIN_DIR=%%~dpD"
if exist "!OLLAMA_BIN_DIR!ollama app.exe" (
    start "" "!OLLAMA_BIN_DIR!ollama app.exe"
) else (
    powershell -NoProfile -Command "Start-Process -FilePath '!OLLAMA_EXE!' -ArgumentList 'serve' -WindowStyle Hidden"
)

set /a TRIES=0
:WAIT_OLLAMA
curl.exe -s -f -o nul "%OLLAMA_API%" >nul 2>&1
if not errorlevel 1 goto :OLLAMA_UP
set /a TRIES+=1
if !TRIES! geq 60 (
    set "ERR=Ollama service did not start."
    goto :FAIL
)
timeout /t 1 /nobreak >nul
goto :WAIT_OLLAMA

:OLLAMA_UP
echo      Ollama service running.

:MODEL
"!OLLAMA_EXE!" list | findstr /i /c:"%MODEL%" >nul
if not errorlevel 1 (
    echo      Model %MODEL% ready.
    goto :RUN_APP
)
echo      Downloading model %MODEL% - first time only, about 5 GB...
"!OLLAMA_EXE!" pull %MODEL%
if errorlevel 1 (
    set "ERR=Could not download model %MODEL%."
    goto :FAIL
)
echo      Model %MODEL% ready.

:: ============================================
:: PASO 4: Abrir la aplicacion (sin consola)
:: ============================================
:RUN_APP
echo.
echo [4/4] Opening TimeSheet Agent...
start "" /d "%APP_DIR%" "%ENV_DIR%\pythonw.exe" "%APP_DIR%app.py"
endlocal
exit /b 0

:FAIL
echo.
echo ERROR: !ERR!
echo.
pause
endlocal
exit /b 1
