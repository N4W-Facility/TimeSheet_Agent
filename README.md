# TimeSheet Agent

**A chat assistant for the N4W Facility team that turns your Outlook calendar into Workday and N4W Facility timesheets, one step at a time, with you approving every step.**

You tag your meetings in Outlook with a project category. The agent reads them, totals your hours per project and day, prorates them where TNC requires it, and fills **Workday** and **N4W Facility** for you. It also tells you what is still missing before you close the month.

The agent works only with your hours and your projects. It never submits anything until you approve it.

---

## What it can do

Write to it the way you would write to a colleague, in **English, Spanish or Portuguese**. To see everything it can do inside the app, ask *"what can you do?"*.

| | What | Try saying |
|---|---|---|
| 🕒 | **Read your hours** from Outlook | *"read my hours for September"* |
| 🏷️ | **Categorize** meetings that have no category (it suggests one from past meetings) | *"help me categorize my meetings of September"* |
| ⚖️ | **Prorate** hours from shared/overhead projects onto your real projects | *"prorate the hours for September"* |
| 🟢 | **Fill Workday** for the period you read (a month, a week or a few days), week by week | *"fill Workday for September"*, *"fill Workday with the hours I read"* |
| 🟦 | **Submit N4W Facility** (Monday–Sunday weeks) | *"submit N4W for September"* |
| ✅ | **Check what's pending** and whether you're ready to close | *"what's pending?"*, *"am I ready to close September?"* |
| ✏️ | **Fix an hour** before uploading | *"put 4 h on OF0104 on Tuesday"* |
| 📊 | **Analysis**: summaries, comparisons, alerts, averages, charts | *"compare September with August"*, *"show me a chart of my hours this year"* |
| 🎯 | **Dedication goals** per project | *"my dedication to OF0104 should be 30%"* |
| 📁 | **My projects**: add or remove them, checked against the global N4W project list | *"which are my projects?"*, *"I no longer work on OF0104"* |
| 🌴 | **Leave & public holidays** (see below) | *"am I ready to close November?"* warns about a forgotten holiday |
| 🧹 | **Clear the chat** (or the 🗑 button). Your hours, projects and history are kept | *"clear chat"*, *"borra el chat"* |

The header shows your progress: **① Read → ② Prorate → ③ Workday · ④ N4W**.

---

## How it works

```
Outlook calendar  (category "CODE | Description" on each meeting)
      │  ① read
      ▼
Hours per project and day ──► ② prorate (only if a project requires it)
      │                              │
      │                              ▼
      │                       ③ Workday: the period read, week by week,
      │                          you approve each week before it is saved
      ▼
④ N4W Facility: full Monday–Sunday weeks, no prorating, you approve the exact rows
```

**TNC rules the agent applies for you:**
- **Workday** takes any period you read: a month, a week or a few days. Workday's screen shows Sunday–Saturday weeks; only the days you read are written and the other days of that week are left as they are.
- **N4W Facility** periods are full Monday–Sunday weeks (1 or more).
- **Prorating** is mandatory for Workday when the period has hours on projects marked *Prorate = 1* in the global project list. You choose which projects receive those hours.
- **Closed projects:** hours on a project before it opened, after it closed, or on a project missing from the global list are blocked from upload. You get a list so you can fix them in Outlook.
- Hours are rounded to **0.25 h**, and the agent expects **8 h per working day**.

### Leave and public holidays

Mark each day off in Outlook as an **8-hour block** (or an all-day event) with a leave category:

| Code | Leave | Code | Leave |
|---|---|---|---|
| XX05 | Public Holiday | XX09 | Vacation (Days) |
| XX08 | Sick (Days) | XX06 | Medical Leave |
| XX07 | TNC Personal Days | XX02 | Administrative Leave Discretionary |
| XX03 | Parental Leave | XX10 | Parental Leave (Not TNC Funded) |
| XX11 | Administrative Leave Legally Required | XX12 | Administrative Leave Mandatory |
| XX13 | Bereavement Leave | XX14 | Leave Without Pay (LWOP) |

- **N4W Facility** receives **8 h** for that day, reported as `OF0104`.
- **Workday** receives **1** (one day) under *Time Type → Absence*. It works the same whatever language your Workday is in.
- The agent creates the leave categories in Outlook if they are missing.
- **Holiday check:** your country is taken from your Windows region, and the agent warns you when a public holiday has no XX05. While filling Workday, it also reads the holidays Workday shows in each day's header and warns you before saving.
- Leave days count toward your daily 8 h but **not** toward your dedication % per project.

---

## Getting started

**You need:** Windows, Outlook (desktop app, signed in), Google Chrome, and your TNC Workday access.

1. Open the [latest release](https://github.com/N4W-Facility/TimeSheet_Agent/releases/latest), download **Source code (zip)** and extract it (right click → *Extract All*).
2. In the extracted folder, double-click **`install.bat`**. It:
   - copies the app to `%LOCALAPPDATA%\TimeSheetAgent` (a hidden folder, so you never have to deal with the code),
   - creates a **TimeSheet Agent** shortcut on your Desktop and in the Start menu (type *"TimeSheet"* in Windows search),
   - adds it to Windows *Installed apps*, with an uninstall option,
   - opens the app. The first run sets everything up, which takes a few minutes: a private Python environment (it does not touch any other Python on your PC), **Ollama** and the local AI model (`qwen3:4b`, which runs without a GPU).

   You can delete the downloaded folder afterwards.
3. On first use, set your email in Settings (⚙). The agent then asks for the project codes you work on. If you used the old projects Excel, you can write *"import my Excel"* instead.
4. Make sure your Outlook meetings carry a category like `OF0104 | Description`. The agent creates the categories for your projects.
5. Start with *"read my hours for <month>"* and follow the suggestions.

**Updates are automatic.** Each time you open the app it checks for a new release and installs it before starting. Your history, settings and files are kept. If there is no internet, or the app is already open, it starts with the version you have.

**Uninstall:** Windows *Settings → Apps → Installed apps → TimeSheet Agent → Uninstall*. It asks whether to keep your hours history and settings. Your files in `Documents\TimeSheetAgent` and Ollama are not removed.

**Filling Workday:** the agent opens Chrome. You sign in to Workday as usual, then the agent navigates to *Enter Time by Type*, fills each week and shows you a confirmation card before it saves. Don't press **Esc** inside the Workday table, because Workday will ask whether to discard your changes.

---

## Privacy

- The AI model runs **on your computer** (Ollama). Your calendar and hours are not sent to any AI service.
- The model only interprets what you write. All calculations, rules and uploads are plain Python code.
- Your history (hours per day and project, goals, what was submitted) is stored locally in `%LOCALAPPDATA%\TimeSheetAgent\history.db`.
- Generated files (`01-Report_*.xlsx`, `02-Timesheet_*.csv`, `03-Timesheet_Prorate_*.csv`) are saved in `Documents\TimeSheetAgent`.
- The global project list (`N4W_Task_Details.xlsx`) is downloaded when the app opens. If there is no network, the app uses the last local copy.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| "Could not reach the language model" | Check that Ollama is running (llama icon in the tray), or open the app again from the Start menu. |
| A category in Outlook is "without a code" | Its name must start with a valid project code: `CODE \| Description`. |
| Hours are blocked | The project is closed, not yet open, or missing from the global list. Move those hours in Outlook and read the month again. |
| Workday picked the wrong task | The confirmation card for that week lists any choice the agent made automatically. Fix it in Workday before approving. |
| A leave type is not in your Workday Absence menu | XX01 (Maternity) and XX04 (Compensation) are not available for everyone. The agent tells you to enter them by hand. |
| Wrong country for holidays | Set `"country"` (two letters, e.g. `"CO"`, `"US"`, `"BR"`) in `%LOCALAPPDATA%\TimeSheetAgent\settings.json`. |

---

## For developers

```
install.bat           installer (copies app\ to %LOCALAPPDATA%\TimeSheetAgent, shortcuts, uninstall entry)
app/TimeSheet_Agent.bat   launcher: update check, Python env, Ollama + model, opens the chat
app/update.ps1        auto-update from the latest GitHub release     app/uninstall.bat
app/app.py            chat app (CustomTkinter)          app/cli.py    command-line flows
app/agent/            intent parsing (Ollama), dialogue, messages (en/es/pt), suggestions
app/pipeline.py       independent steps with callbacks (read, prorate, Workday, N4W)
app/core/             Outlook (COM), prorating, N4W Excel, analysis, history, holidays, charts
app/core/workday/     Playwright automation over Chrome (CDP), language-independent selectors
app/tests/            pytest suite        app/eval_intents.py   intent accuracy per model
```

- Development: run `app\TimeSheet_Agent.bat` from the repository. It never auto-updates; only the installed copy does.
- Run the tests with the app's environment, from `app\`: `%LOCALAPPDATA%\TimeSheetAgent\mamba\envs\timesheet-agent\python.exe -m pytest tests`.
- After changing the model prompt in `app/agent/llm.py`, run `eval_intents.py`. Small models are sensitive to prompt wording.
- `CLAUDE.md` documents the architecture and the domain rules in detail.

### Publishing a new version

1. Push your changes to `main`.
2. On GitHub: *Releases → Draft a new release*, create a tag such as `v1.1`, add a short note and click *Publish release*.

That is all. Everyone's app updates the next time they open it. The release ZIP holds only `install.bat`, `README.md` and `app\`. Tests, `eval_intents.py` and `CLAUDE.md` are left out through `export-ignore` in `.gitattributes`.

The update downloads the release from the public GitHub URL, so **the repository must be public**. With a private repository, installs and updates fail. The app still opens, but stays on the version it has.

---

*Built for the N4W Facility team at The Nature Conservancy.*
