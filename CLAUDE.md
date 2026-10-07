# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TimeSheet Agent unifica dos herramientas previas de TNC (Nature For Water):
- `App_TimeSheet_N4W.py` (monolito Tkinter: Outlook → BD de códigos → N4W Facility; Deltek eliminado). El agente ya NO usa el Excel de proyectos del usuario: "mis proyectos" se arman en el chat.
- `Workday_Tool` (Playwright sobre Chrome CDP para llenar Workday)

Ambos originales siguen en `C:\WSL\Workday_Tool` como respaldo; no se modifican.

El usuario conversa con un agente limitado a **sus horas y los proyectos a los que carga tiempo**. El flujo es **paso a paso y lo controla el usuario** (nunca "hazlo todo"): leer Outlook → prorratear (obligatorio si aplica) → llenar Workday / enviar N4W; cada paso muestra el balance y pide aprobación. Además responde análisis sobre un historial local que crece mes a mes (resúmenes, comparaciones, promedios, objetivos de dedicación, alertas). El LLM (Ollama, `qwen3:4b`, liviano para equipos sin GPU) solo clasifica el mensaje; nunca navega ni calcula horas.

## Entorno

Se desarrolla en WSL pero **se ejecuta en Python de Windows** (Outlook y Excel vía `win32com`). Los módulos importan `win32com` (Outlook) dentro de las funciones, así que `core/` se puede importar y testear en Linux.

**Usuarios finales**: doble clic en `TimeSheet_Agent.bat`. Instala/verifica en `%LOCALAPPDATA%\TimeSheetAgent\` micromamba (exe suelto) y el ambiente `timesheet-agent` (se recrea si cambia el hash de `environment.yml`), instala Ollama si falta, arranca el servicio, descarga el modelo y abre `app.py` con `pythonw.exe` (sin consola; errores de arranque → ventana + `app.log`). Con `TSA_OLLAMA_HOST` definido se salta Ollama local. El `.bat` debe quedar en CRLF (`.gitattributes`). No hace falta `playwright install`: Playwright se conecta por CDP al Chrome del usuario.

**Python fijado a 3.11.13**: el EDR de TNC bloqueó ("Acceso denegado", archivo ilegible) el `python.exe` de 3.11.17, publicado el mismo día. No subir de versión sin probar en una máquina corporativa.

Desarrollo (Windows):
```powershell
$env:MAMBA_ROOT_PREFIX="$env:LOCALAPPDATA\TimeSheetAgent\mamba"
& "$env:LOCALAPPDATA\TimeSheetAgent\micromamba.exe" run -n timesheet-agent python app.py
python -m pytest tests -q          # (dentro del ambiente) sin Outlook/Ollama/navegador; también corre en WSL
python -m pytest tests/test_agent.py::test_agent_routes_workday_month   # un test
python cli.py report  --month 2026-10                # archivos en --workdir (def. Documents\TimeSheetAgent)
python cli.py workday --month 2026-10               # prorratea si hay proyectos Prorate=1
python cli.py n4w     --start 2026-10-05 --end 2026-10-25 --email me@tnc.org
python cli.py categories                            # categorías Outlook de "mis proyectos"
python eval_intents.py qwen3:1.7b qwen3:4b qwen3:8b   # precisión/velocidad de modelos (Ollama local)
```
Ollama: `TSA_OLLAMA_HOST` / `TSA_OLLAMA_MODEL` (no `OLLAMA_HOST`, que en el servidor suele ser `0.0.0.0`). `settings.json` (email, idioma; `db_path` solo del Excel antiguo para importarlo una vez) lo crea la UI y está en `.gitignore`.

## Architecture

```
core/          lógica sin GUI: devuelve datos o lanza excepciones (nunca messagebox)
pipeline.py    Pipeline: un método por paso, cada uno recibe su periodo + Callbacks(log, decide, approve)
workflows.py   flujos completos deterministas (Workday por mes, N4W por semanas, reporte)
cli.py         workflows + callbacks por consola
core/analysis.py  funciones puras sobre formato largo [day, code, task_name, hours]: balance, comparación, promedios, alertas, stats de prorrateo
core/database.py  base global N4W_Task_Details (Box): task_status, catalog (+ XX internos de config), extract_codes, legacy_codes
core/history.py   SQLite en %LOCALAPPDATA%\TimeSheetAgent\history.db: hours (source outlook|prorated), targets, events, projects (mis proyectos), dismissed
agent/llm.py   Ollama: parse_intent() → Intent (JSON con esquema, temperature 0, think=False); UNA llamada por mensaje
agent/suggest.py frases sugeridas según el paso (autocompletar, pista "Next", progreso ①②③) en en/es/pt; nunca ejecutan, solo se escriben en el campo
agent/i18n.py  mensajes fijos del agente traducidos estáticamente (en/es/pt; otros idiomas → en)
agent/agent.py Intent → do_<acción>: pasos con estado de sesión (Loaded) + análisis del historial
ui/chat_app.py chat CustomTkinter (paleta Zinc); implementa AgentUI (say/log/show/decide/approve); sin botones de acción: todo es lenguaje natural + autocompletar (Tab/↑↓)
eval_intents.py casos multilenguaje para comparar modelos
```

**Callbacks son el contrato central.** `Pipeline` nunca pregunta directamente: emite `Decision(kind, question, options, multi)` vía `decide` y pide confirmaciones vía `approve(title, detail)`. CLI y chat implementan los mismos callbacks. Los logs de `core.*` (módulo `logging`) se redirigen a `callbacks.log`.

**El LLM solo clasifica.** `parse_intent` devuelve acción + periodo/proyecto/objetivo + `reply` corto en el idioma del usuario (sin números); todo lo demás (fechas, reglas, cálculos, ejecución) es Python. Mensajes fijos: `agent/i18n.py`. Tablas, tarjetas y títulos: inglés.

**Pasos con estado.** `do_read_hours` guarda el periodo en `Agent.loaded`; `prorate`/`fill_workday` lo exigen y validan el orden (Workday: solo mes calendario y, si hay proyectos Prorate=1, solo tras prorratear). La base global se descarga de Box al abrir (`check_global`, con copia local si no hay red). Cada lectura guarda en el historial; el prorrateo guarda `source='prorated'`, que es lo que el análisis cuenta como "cargado" ese mes. Al abrir la app, `Agent.greet()` saluda (idioma persistido en `settings.json`), descarga la base global, arma "mis proyectos" la primera vez (`onboard`: importa el Excel antiguo si `settings.db_path` existe; si no, pregunta los códigos o "importar mi Excel" → `AgentUI.pick_file` abre el explorador y se recuerda la ruta), los revisa (`review_projects`) y `Agent.resume()` reconstruye `loaded` desde el último evento `read` del historial + los CSV en disco y anuncia el siguiente paso (nada si ya se llenó Workday). El hilo de trabajo de la UI llama `pythoncom.CoInitialize()` (COM fuera del hilo principal). En la UI, `decide`/`approve` bloquean el hilo del agente con `threading.Event` hasta que el usuario pulsa la tarjeta.

Flujo de datos:
```
Outlook (categoría "CODE | Desc") → outlook.build_timesheet + catálogo (Task Details + XX)
  → 02-Timesheet_<start>_<end>.csv [Code, Task Name, Grant ID, fechas 'YYYY-MM-DD HH:MM:SS']
  → Workday: mes calendario → prorate (obligatorio si hay Prorate=1 en Task Details) → 03-Timesheet_Prorate_<...>.csv → Playwright
  → N4W: semanas lun–dom, SIN prorrateo → Excel → OneDrive
```
Los archivos (`N4W_Task_Details.xlsx`, CSVs) viven en `config.WORK_DIR` (Documents\TimeSheetAgent).

## Reglas de dominio no obvias

- **Periodos (regla TNC)**: Workday = mes calendario, día 1 → último (`month_bounds`). N4W = 1..n semanas completas lunes–domingo (`validate_complete_weeks`); con solo un mes, el usuario elige semanas consecutivas (`choose_n4w_weeks`). Dentro de Workday la UI agrupa domingo–sábado (`csv_reader.py`), así que la primera y la última semana del mes quedan parciales.
- **Códigos `XX*`** (licencias XX01–XX14, fijos en `config.INTERNAL_CODES`): no están en Task Details, no se prorratean, no cuentan en el % de dedicación. El usuario marca cada día libre en Outlook como bloque de 8 h (un evento de día completo cuenta 8 h por día lun–vie, `outlook.all_day_entries`). Internamente (CSV, historial) quedan en 8 h; N4W los reporta como `OF0104` con 8 h; Workday recibe 1 (día) — la conversión la hace `csv_reader.parse_csv`. En Workday van en Tipo de jornada → submenú Ausencia y se eligen por id (`WORKDAY_ABSENCE_IDS`, igual en todo idioma); XX01/XX04 no tienen id (se avisa en la confirmación). Las categorías XX se crean en Outlook al abrir si faltan.
- **Festivos**: país = región de Windows (`holidays_cal.detect_country`, guardado en `settings.country`), festivos con la librería `holidays`; al leer y en `close_check` se avisan festivos sin XX05. Al llenar Workday se leen los festivos de la cabecera de cada día (`ghostCell_c4..c10`, texto entre paréntesis) y se avisan en la confirmación de la semana.
- **Prorrateo**: obligatorio para Workday cuando el mes tiene horas en códigos con `Prorate=1` en `N4W_Task_Details.xlsx`; el usuario elige qué proyectos reales reciben las horas.
- **Mis proyectos** (`history.projects`): solo códigos activos de Task Details (con `Date_Opened`, sin `Date_Closed`); al agregar se crea la categoría `CODE | Description` en Outlook; al quitar se conserva. Tras leer un mes y al abrir, `analysis.review_projects` propone (tarjeta con casillas premarcadas): quitar cerrados/inexistentes, quitar sin horas en `REVIEW_IDLE_MONTHS` meses, agregar activos con horas fuera de la lista. Lo desmarcado no se repite en `REVIEW_SNOOZE_DAYS`.
- **Preguntas en conversación**: respuestas cortas ("30%", "40 h", "igual", "omitir", códigos) se interpretan en Python sin LLM (`_answer_target`, `_answer_codes`); otra cosa va al LLM. Selecciones múltiples (prorrateo, agregar/quitar proyectos, revisión) usan tarjetas con casillas.
- **Estado y control** (`do_status`, `do_close_check`): salen de la tabla `events` (cobertura de semanas Workday dom–sáb y N4W lun–dom); los eventos `workday`/`n4w` guardan en `detail` lo enviado (auditoría "¿qué envié?"). Un saludo a secas (`GREETINGS`) muestra el estado sin LLM. `close_check` = días < 8 h + reuniones sin categoría (Outlook) + horas bloqueadas + pasos.
- **Correcciones** (`do_edit_hours`): cambian solo el CSV que va a Workday (prorrateado si existe) y el historial; Outlook no se toca, así que volver a leer descarta la edición y N4W (que relee Outlook) no la ve. Preguntas puntuales de `hours_summary` (con proyecto o rango < 7 días) responden en una frase; un periodo en curso o no leído se lee de Outlook hasta hoy sin guardar.
- **Alertas**: horas esperadas = días lun–vie × 8 (sin festivos); tolerancias en `config.py`.
- **Códigos `TNC*`**: se excluyen del Excel N4W.
- **Horas** se redondean a 0.25. Workday usa coma decimal (`format_hours`).
- **OneDrive**: el destino real es `<padre de OneDrive>\The Nature Conservancy\N4WTimeTracking - Science Timesheets` (biblioteca SharePoint sincronizada); `put_file_in_onedrive` conserva ese hack heredado.

## Estado de Workday (heredado, pendiente fase 3)

- `run()` asume que el usuario ya abrió "Introducción de horas por tipo" en la **primera semana**; los métodos de navegación existen pero no se llaman.
- Semanas consecutivas: `go_to_next_week()` avanza de a una.
- `add_project_row` escribe el Task Name + Enter. Con un resultado Workday lo elige solo; con varios (búsqueda por palabras: "IS General Admin" también trae "… > Admin") `_pick_task` elige la opción cuyo último tramo (tras `>`, sin "(Comienza el…)") más coincide (`core/workday/matching.py`), lo anota en la confirmación de la semana y verifica que la fila quedó con tipo de jornada antes de escribir horas. No usar Escape en la tabla: abre "¿Descartar cambios?".
- Pendiente: si `add_project_row` falla, el reintento añade otra fila (la fallida queda).
- Selectores con texto español (`placeholder="Buscar"`); idioma fijo en "es".

## Fases

1. ✅ Extraer `core/` + pipeline con callbacks + CLI.
2. ✅ Chat + agente Ollama (intención multilenguaje, UI en inglés).
2b. ✅ Flujo paso a paso, prorrateo obligatorio, historial SQLite + análisis/objetivos/alertas, modelo `qwen3:4b`.
2c. ✅ Sin Excel de proyectos: base global al abrir, "mis proyectos" conversacional con revisión proactiva, tarjeta Projects, preguntas de dedicación.
3. Robustecer Workday: navegación automática, punto de decisión con `rules.json` (regla → LLM → usuario) para código ambiguo, categoría Outlook sin código, días incompletos.
