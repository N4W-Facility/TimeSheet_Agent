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

```powershell
conda env create -f environment.yml
conda activate timesheet-agent
playwright install chromium
python -m pytest tests -q          # partes puras, también corren en WSL
python cli.py report --db C:\ruta\DataBase.xlsx --month 2026-10
python cli.py all    --db ... --month 2026-10 --email yo@tnc.org [--prorate]
```

## Architecture

```
core/         lógica sin GUI: devuelve datos o lanza excepciones (nunca messagebox)
pipeline.py   Pipeline: un método por paso + Callbacks(log, decide, approve)
cli.py        responde los callbacks por consola (fase 1)
```

**Callbacks son el contrato central.** `Pipeline` nunca pregunta directamente: emite `Decision(kind, question, options, multi)` vía `decide` y pide confirmaciones vía `approve(title, detail)`. La CLI, una futura GUI y el agente Ollama implementan los mismos callbacks; el pipeline no cambia al agregar el agente. Los logs de `core.*` (módulo `logging`) se redirigen a `callbacks.log`.

Flujo de datos:
```
Outlook (categoría "CODE | Desc") → outlook.build_timesheet + BD (hoja N4W-Projects)
  → 02-Timesheet.csv [Code, Task Name, Grant ID, fechas 'YYYY-MM-DD HH:MM:SS']
  → (opcional) prorate → 03-Timesheet_Prorate.csv → Workday
  → N4W usa SIEMPRE 02-Timesheet.csv (sin prorrateo) → Excel → OneDrive
```
Todos los archivos (BD, `N4W_Task_Details.xlsx` de Box, CSVs) viven en la carpeta de la BD del usuario.

## Reglas de dominio no obvias

- **Semanas distintas**: N4W exige rangos lunes–domingo (`align_to_full_weeks`); Workday agrupa domingo–sábado (`core/workday/csv_reader.py`). Un mes N4W genera una semana Workday extra con el último domingo.
- **Códigos `XX*`**: no se sincronizan con Box, no se prorratean, en el prorrateo horas > 0 pasan a 1, y en N4W se reportan como `OF0104`.
- **Códigos `TNC*`**: se excluyen del Excel N4W.
- **Horas** se redondean a 0.25. Workday usa coma decimal (`format_hours`).
- **BD local**: hoja protegida (contraseña en `config.py`) con fórmulas → se escribe con Excel COM, no openpyxl.
- **OneDrive**: el destino real es `<padre de OneDrive>\The Nature Conservancy\N4WTimeTracking - Science Timesheets` (biblioteca SharePoint sincronizada); `put_file_in_onedrive` conserva ese hack heredado.

## Estado de Workday (heredado, pendiente fase 2)

- `run()` asume que el usuario ya abrió "Introducción de horas por tipo" en la **primera semana**; los métodos de navegación existen pero no se llaman.
- Semanas consecutivas: `go_to_next_week()` avanza de a una.
- `add_project_row` escribe el Task Name + Enter → elige la **primera** opción a ciegas (caso OF0104 con varias opciones = primer punto de decisión del agente).
- Selectores con texto español (`placeholder="Buscar"`); idioma fijo en "es".

## Fases

1. ✅ Extraer `core/` + pipeline con callbacks + CLI.
2. Robustecer Workday: navegación automática, punto de decisión con `rules.json` (regla → LLM → usuario).
3. Agente Ollama (`config.OLLAMA_*`) + chat. Decisiones del LLM: código ambiguo en Workday, categoría Outlook sin código, días incompletos. Una sola aprobación del resumen antes de Workday.
