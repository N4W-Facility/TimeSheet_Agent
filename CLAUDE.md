# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TimeSheet Agent unifica dos herramientas previas de TNC (Nature For Water):
- `App_TimeSheet_N4W.py` (monolito Tkinter: Outlook → BD de códigos → N4W Facility; Deltek eliminado)
- `Workday_Tool` (Playwright sobre Chrome CDP para llenar Workday)

Ambos originales siguen en `C:\WSL\Workday_Tool` como respaldo; no se modifican.

Objetivo final: el usuario escribe en un chat "llena octubre" y un **pipeline guiado** hace todo. El LLM (Ollama, `qwen3:8b`) solo interpreta el chat y decide en puntos concretos; nunca navega ni calcula horas.

## Entorno

Se desarrolla en WSL pero **se ejecuta en Python de Windows** (Outlook y Excel vía `win32com`). Los módulos importan `win32com` dentro de las funciones, así que `core/` se puede importar y testear en Linux.

**Usuarios finales**: doble clic en `TimeSheet_Agent.bat`. Instala/verifica en `%LOCALAPPDATA%\TimeSheetAgent\` micromamba (exe suelto) y el ambiente `timesheet-agent` (se recrea si cambia el hash de `environment.yml`), instala Ollama si falta, arranca el servicio, descarga el modelo y abre `app.py` con `pythonw.exe` (sin consola; errores de arranque → ventana + `app.log`). Con `TSA_OLLAMA_HOST` definido se salta Ollama local. El `.bat` debe quedar en CRLF (`.gitattributes`). No hace falta `playwright install`: Playwright se conecta por CDP al Chrome del usuario.

**Python fijado a 3.11.13**: el EDR de TNC bloqueó ("Acceso denegado", archivo ilegible) el `python.exe` de 3.11.17, publicado el mismo día. No subir de versión sin probar en una máquina corporativa.

Desarrollo (Windows):
```powershell
$env:MAMBA_ROOT_PREFIX="$env:LOCALAPPDATA\TimeSheetAgent\mamba"
& "$env:LOCALAPPDATA\TimeSheetAgent\micromamba.exe" run -n timesheet-agent python app.py
python -m pytest tests -q          # (dentro del ambiente) sin Outlook/Ollama/navegador; también corre en WSL
python -m pytest tests/test_agent.py::test_agent_routes_workday_month   # un test
python cli.py report  --db C:\ruta\DataBase.xlsx --month 2026-10
python cli.py workday --db ... --month 2026-10 [--prorate]
python cli.py n4w     --db ... --start 2026-10-05 --end 2026-10-25 --email me@tnc.org
```
Ollama: `TSA_OLLAMA_HOST` / `TSA_OLLAMA_MODEL` (no `OLLAMA_HOST`, que en el servidor suele ser `0.0.0.0`). `settings.json` (ruta BD + email) lo crea la UI y está en `.gitignore`.

## Architecture

```
core/          lógica sin GUI: devuelve datos o lanza excepciones (nunca messagebox)
pipeline.py    Pipeline: un método por paso, cada uno recibe su periodo + Callbacks(log, decide, approve)
workflows.py   flujos completos deterministas (Workday por mes, N4W por semanas, reporte)
cli.py         workflows + callbacks por consola
agent/llm.py   Ollama: parse_intent() → Intent (JSON con esquema, temperature 0, think=False); localize()
agent/agent.py Intent → validación en Python → workflows; adapta callbacks a la UI y traduce
ui/chat_app.py chat CustomTkinter (paleta Zinc); implementa AgentUI (say/log/decide/approve)
```

**Callbacks son el contrato central.** `Pipeline` nunca pregunta directamente: emite `Decision(kind, question, options, multi)` vía `decide` y pide confirmaciones vía `approve(title, detail)`. CLI y chat implementan los mismos callbacks. Los logs de `core.*` (módulo `logging`) se redirigen a `callbacks.log`.

**El LLM solo clasifica.** `parse_intent` devuelve acción + periodo + `reply` en el idioma del usuario; todo lo demás (fechas, reglas, ejecución) es Python. Mensajes del sistema se escriben en inglés y pasan por `Agent.t()` (traducción vía LLM con caché). Tablas/detalles de aprobación no se traducen. En la UI, `decide`/`approve` bloquean el hilo del agente con `threading.Event` hasta que el usuario pulsa la tarjeta.

Flujo de datos:
```
Outlook (categoría "CODE | Desc") → outlook.build_timesheet + BD (hoja N4W-Projects)
  → 02-Timesheet_<start>_<end>.csv [Code, Task Name, Grant ID, fechas 'YYYY-MM-DD HH:MM:SS']
  → Workday: mes calendario → (opcional) prorate → 03-Timesheet_Prorate_<...>.csv → Playwright
  → N4W: semanas lun–dom, SIN prorrateo → Excel → OneDrive
```
Todos los archivos (BD, `N4W_Task_Details.xlsx` de Box, CSVs) viven en la carpeta de la BD del usuario.

## Reglas de dominio no obvias

- **Periodos (regla TNC)**: Workday = mes calendario, día 1 → último (`month_bounds`). N4W = 1..n semanas completas lunes–domingo (`validate_complete_weeks`); con solo un mes, el usuario elige semanas consecutivas (`choose_n4w_weeks`). Dentro de Workday la UI agrupa domingo–sábado (`csv_reader.py`), así que la primera y la última semana del mes quedan parciales.
- **Códigos `XX*`**: no se sincronizan con Box, no se prorratean, en el prorrateo horas > 0 pasan a 1, y en N4W se reportan como `OF0104`.
- **Códigos `TNC*`**: se excluyen del Excel N4W.
- **Horas** se redondean a 0.25. Workday usa coma decimal (`format_hours`).
- **BD local**: hoja protegida (contraseña en `config.py`) con fórmulas → se escribe con Excel COM, no openpyxl.
- **OneDrive**: el destino real es `<padre de OneDrive>\The Nature Conservancy\N4WTimeTracking - Science Timesheets` (biblioteca SharePoint sincronizada); `put_file_in_onedrive` conserva ese hack heredado.

## Estado de Workday (heredado, pendiente fase 3)

- `run()` asume que el usuario ya abrió "Introducción de horas por tipo" en la **primera semana**; los métodos de navegación existen pero no se llaman.
- Semanas consecutivas: `go_to_next_week()` avanza de a una.
- `add_project_row` escribe el Task Name + Enter → elige la **primera** opción a ciegas (caso OF0104 con varias opciones = primer punto de decisión del agente).
- Selectores con texto español (`placeholder="Buscar"`); idioma fijo en "es".

## Fases

1. ✅ Extraer `core/` + pipeline con callbacks + CLI.
2. ✅ Chat + agente Ollama (intención multilenguaje, UI en inglés).
3. Robustecer Workday: navegación automática, punto de decisión con `rules.json` (regla → LLM → usuario) para código ambiguo, categoría Outlook sin código, días incompletos.
