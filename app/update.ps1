# ============================================================
# ACTUALIZACION AUTOMATICA (la llama TimeSheet_Agent.bat al abrir)
#   Compara la version instalada con el ultimo release de GitHub y,
#   si hay uno nuevo, reemplaza app\ con el app\ del release.
#   Nunca bloquea: sin internet o con la app abierta sigue con la version actual.
#   Datos del usuario (history.db, settings.json, mamba\) quedan fuera de app\.
# ============================================================
param([Parameter(Mandatory = $true)][string]$TsaHome,
      [string]$Repo = 'https://github.com/N4W-Facility/TimeSheet_Agent')   # otro solo para pruebas

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$AppDir = Join-Path $TsaHome 'app'
$VersionFile = Join-Path $TsaHome 'version.txt'
$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\TimeSheetAgent'

function Norm([string]$v) { return $v.Trim().TrimStart('v', 'V') }

try {
    # curl.exe (viene con Windows) y no .NET: en equipos con proxy/EDR la conexion .NET se corta.
    # /releases/latest redirige a /releases/tag/<tag> (sin limite de consultas, a diferencia de la API)
    $location = & curl.exe -s -o NUL -w '%{redirect_url}' -m 8 "$Repo/releases/latest"
    if ($LASTEXITCODE -ne 0) { throw "no connection to GitHub (curl $LASTEXITCODE)" }
    if (-not $location -or $location -notmatch '/releases/tag/([^/?#]+)') {
        Write-Host '     No release published yet.'
        exit 0
    }
    $tag = [Uri]::UnescapeDataString($Matches[1])

    $current = ''
    if (Test-Path $VersionFile) { $current = (Get-Content $VersionFile -Raw) }
    if ((Norm $current) -eq (Norm $tag)) {
        Write-Host "     Up to date ($tag)."
        exit 0
    }

    Write-Host "     New version $tag - downloading..."
    $tmp = Join-Path $env:TEMP ('TimeSheetAgent_update_' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    try {
        $zip = Join-Path $tmp 'release.zip'
        & curl.exe -L --fail -s -m 300 -o $zip "$Repo/archive/refs/tags/$tag.zip"
        if ($LASTEXITCODE -ne 0) { throw "download failed (curl $LASTEXITCODE)" }
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        $root = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
        $newApp = Join-Path $root.FullName 'app'
        if (-not (Test-Path (Join-Path $newApp 'app.py'))) { throw 'The release does not contain app\app.py.' }

        # cambio de carpetas: si app\ esta en uso (la app abierta) no se toca nada
        $old = "$AppDir.old"
        if (Test-Path $old) { Remove-Item $old -Recurse -Force }
        try {
            Rename-Item -Path $AppDir -NewName (Split-Path $old -Leaf)
        } catch {
            Write-Host '     TimeSheet Agent is open - close it to update. Using the current version.'
            exit 0
        }
        try {
            Move-Item -Path $newApp -Destination $AppDir
        } catch {
            Rename-Item -Path $old -NewName (Split-Path $AppDir -Leaf)   # vuelve a la version anterior
            throw
        }
        Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue

        Set-Content -Path $VersionFile -Value $tag -NoNewline
        if (Test-Path $UninstallKey) { Set-ItemProperty -Path $UninstallKey -Name DisplayVersion -Value (Norm $tag) }
        Write-Host "     Updated to $tag."
    } finally {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
} catch {
    Write-Host "     Could not check for updates ($($_.Exception.Message)). Using the current version."
}
exit 0
