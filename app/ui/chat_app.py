# ============================================================
# CHAT — CustomTkinter / Zinc Dark Theme (misma paleta que Workday_Tool)
# La UI está en inglés; el agente responde en el idioma del usuario.
# El agente corre en un hilo; decide/approve bloquean ese hilo
# hasta que el usuario responde en la tarjeta (threading.Event).
# ============================================================
import os
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

import config
from agent import llm, suggest
from agent.agent import Agent
from agent.settings import Settings
from pipeline import Decision

# ── Paleta ───────────────────────────────────────────────────
BG         = "#09090b"
CARD_BG    = "#111113"
BORDER     = "#27272a"
TEXT       = "#fafafa"
MUTED      = "#71717a"
BLUE       = "#3b82f6"
BLUE_HOV   = "#2563eb"
GREEN      = "#22c55e"
GREEN_HOV  = "#16a34a"
AMBER      = "#f59e0b"
RED        = "#ef4444"
RED_HOV    = "#dc2626"
INPUT_BG   = "#18181b"
LOG_BG     = "#0d0d0d"
LOG_FG     = "#00ff88"

FONT       = "Segoe UI"
MONO       = "Consolas"
WRAP       = 470

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

MAX_DROPDOWN = 5


def _com_init():
    try:
        import pythoncom
    except ImportError:          # Linux/tests
        return None
    pythoncom.CoInitialize()
    return pythoncom


class ChatApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("TimeSheet Agent")
        try:
            self.root.iconbitmap(os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico"))
        except tk.TclError:                       # sin icono la app funciona igual
            pass
        self.root.geometry("680x780")
        self.root.minsize(560, 600)
        self.root.configure(fg_color=BG)

        self.settings = Settings.load()
        llm.set_model(self.settings.model)
        self.agent = Agent(ui=self, settings=self.settings)
        self.busy = False
        self.log_visible = False
        self.tips = []            # frases sugeridas según el paso actual
        self.dd_items = []        # autocompletado visible
        self.dd_index = -1

        self._build_ui()
        threading.Thread(target=self._check_ollama, daemon=True).start()
        self.root.after(200, lambda: self._run_agent(self.agent.greet))
        if self.settings.missing():
            self.root.after(400, self._open_settings)

    # ── Construcción ─────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self.root, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(18, 8))
        left = ctk.CTkFrame(hdr, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="TimeSheet Agent", font=(FONT, 20, "bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(left, text="Timesheet hours & projects assistant", font=(FONT, 11),
                     text_color=MUTED).pack(anchor="w")
        self.lbl_progress = ctk.CTkLabel(left, text="", font=(FONT, 11), text_color=BLUE)
        self.lbl_progress.pack(anchor="w", pady=(4, 0))

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkButton(right, text="⚙", width=34, height=30, font=(FONT, 14),
                      fg_color=CARD_BG, hover_color=BORDER, border_color=BORDER,
                      border_width=1, corner_radius=6,
                      command=self._open_settings).pack(side="right", padx=(8, 0))
        self.btn_clear = ctk.CTkButton(right, text="🗑", width=34, height=30, font=(FONT, 14),
                                       fg_color=CARD_BG, hover_color=BORDER, border_color=BORDER,
                                       border_width=1, corner_radius=6, command=self._clear_chat)
        self.btn_clear.pack(side="right", padx=(8, 0))
        # Clic en el modelo → elegir otro instalado en Ollama (opción discreta)
        self.lbl_model = ctk.CTkLabel(right, text=f"●  {llm.current_model()}",
                                      font=(FONT, 11), text_color=MUTED, cursor="hand2")
        self.lbl_model.pack(side="right")
        self.lbl_model.bind("<Button-1>", self._model_menu)

        # Barra inferior (se empaqueta antes del chat para reservar espacio)
        bottom = ctk.CTkFrame(self.root, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=20, pady=(4, 16))

        self.log_box = ctk.CTkTextbox(bottom, height=140, font=(MONO, 10), fg_color=LOG_BG,
                                      text_color=LOG_FG, border_color=BORDER, border_width=1,
                                      corner_radius=6, state="disabled", wrap="word")

        bar = ctk.CTkFrame(bottom, fg_color="transparent")
        bar.pack(side="bottom", fill="x")
        self.entry = ctk.CTkEntry(bar, height=40, font=(FONT, 12), text_color=TEXT,
                                  fg_color=INPUT_BG, border_color=BORDER, corner_radius=8,
                                  placeholder_text="Type an instruction (any language)...")
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry.bind("<Return>", self._on_return)
        self.entry.bind("<Tab>", self._on_tab)
        self.entry.bind("<Down>", lambda e: self._move(1))
        self.entry.bind("<Up>", lambda e: self._move(-1))
        self.entry.bind("<Escape>", lambda e: self._hide_dropdown())
        self.entry.bind("<KeyRelease>", self._on_type)
        self.btn_send = ctk.CTkButton(bar, text="Send  ➤", width=90, height=40,
                                      font=(FONT, 12, "bold"), fg_color=BLUE,
                                      hover_color=BLUE_HOV, corner_radius=8, command=self._send)
        self.btn_send.pack(side="left")

        # Siguiente paso sugerido (Tab lo escribe en el campo)
        self.lbl_hint = ctk.CTkLabel(bottom, text="", font=(FONT, 11), text_color=MUTED,
                                     anchor="w", justify="left")
        self.lbl_hint.pack(side="bottom", fill="x", pady=(0, 4))

        status_row = ctk.CTkFrame(bottom, fg_color="transparent")
        status_row.pack(side="bottom", fill="x", pady=(0, 6))
        self.lbl_status = ctk.CTkLabel(status_row, text="●  Ready", font=(FONT, 11),
                                       text_color=MUTED)
        self.lbl_status.pack(side="left")
        self.btn_log = ctk.CTkButton(status_row, text="▸ Details", width=80, height=24,
                                     font=(FONT, 11), fg_color="transparent",
                                     hover_color=BORDER, text_color=MUTED,
                                     command=self._toggle_log)
        self.btn_log.pack(side="right")

        # Chat
        self.chat = ctk.CTkScrollableFrame(self.root, fg_color=BG, corner_radius=0)
        self.chat.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        # Autocompletado: lista flotante sobre el campo de texto
        self.dropdown = ctk.CTkFrame(self.root, fg_color=CARD_BG, border_color=BORDER,
                                     border_width=1, corner_radius=8)

    # ── Sugerencias y autocompletado ─────────────────────────

    def _refresh_suggestions(self):
        """Tras cada turno: frases del paso actual, pista y progreso."""
        try:
            self.tips = self.agent.suggestions()
            progress = self.agent.progress()
        except Exception as e:          # nunca debe romper el chat
            self.log(f"Suggestions unavailable: {e}")
            self.tips, progress = [], ""
        self.lbl_progress.configure(text=progress)
        self._update_hint()

    def _update_hint(self):
        empty = not self.entry.get()
        text = f"Next:  {self.tips[0]}     ⇥ Tab" if self.tips and empty and not self.busy else ""
        self.lbl_hint.configure(text=text)

    def _on_type(self, event):
        if event.keysym in ("Up", "Down", "Tab", "Return", "Escape"):
            return
        self._update_hint()
        text = self.entry.get()
        items = suggest.match(text, self.tips, MAX_DROPDOWN) if not self.busy else []
        if items:
            self._show_dropdown(items)
        else:
            self._hide_dropdown()

    def _show_dropdown(self, items):
        self.dd_items, self.dd_index = items, -1
        for w in self.dropdown.winfo_children():
            w.destroy()
        width = self.entry.winfo_width()
        self.dd_labels = []
        for text in items:
            lbl = ctk.CTkLabel(self.dropdown, text=text, font=(FONT, 12), text_color=TEXT,
                               anchor="w", width=width - 12, height=28, corner_radius=6,
                               fg_color="transparent")
            lbl.pack(fill="x", padx=5, pady=1)
            lbl.bind("<Button-1>", lambda e, t=text: self._accept(t))
            self.dd_labels.append(lbl)
        self.root.update_idletasks()
        x = self.entry.winfo_rootx() - self.root.winfo_rootx()
        y = self.entry.winfo_rooty() - self.root.winfo_rooty() - 4
        self.dropdown.place(x=x, y=y, anchor="sw")
        self.dropdown.lift()

    def _hide_dropdown(self):
        self.dropdown.place_forget()
        self.dd_items, self.dd_index = [], -1

    def _move(self, step: int):
        if not self.dd_items:
            return "break"
        self.dd_index = (self.dd_index + step) % len(self.dd_items)
        for i, lbl in enumerate(self.dd_labels):
            lbl.configure(fg_color=BORDER if i == self.dd_index else "transparent")
        return "break"

    def _accept(self, text: str):
        self.entry.delete(0, "end")
        self.entry.insert(0, text)
        self.entry.icursor("end")
        self.entry.focus_set()
        self._hide_dropdown()
        self._update_hint()

    def _on_tab(self, event):
        if self.dd_items:
            self._accept(self.dd_items[max(self.dd_index, 0)])
        elif not self.entry.get() and self.tips:
            self._accept(self.tips[0])
        return "break"      # no mover el foco

    def _on_return(self, event):
        if self.dd_items and self.dd_index >= 0:
            self._accept(self.dd_items[self.dd_index])
        else:
            self._send()
        return "break"

    # ── Burbujas y tarjetas ──────────────────────────────────

    def _scroll_bottom(self):
        self.root.update_idletasks()
        self.chat._parent_canvas.yview_moveto(1.0)

    def _user_bubble(self, text: str):
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.pack(fill="x", pady=4, padx=8)
        bubble = ctk.CTkFrame(row, fg_color=BLUE, corner_radius=10)
        bubble.pack(side="right")
        ctk.CTkLabel(bubble, text=text, font=(FONT, 12), text_color=TEXT,
                     wraplength=WRAP, justify="left").pack(padx=12, pady=8)
        self._scroll_bottom()

    def _agent_bubble(self, text: str, color: str = TEXT):
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.pack(fill="x", pady=4, padx=8)
        bubble = ctk.CTkFrame(row, fg_color=CARD_BG, border_color=BORDER,
                              border_width=1, corner_radius=10)
        bubble.pack(side="left")
        ctk.CTkLabel(bubble, text=text, font=(FONT, 12), text_color=color,
                     wraplength=WRAP, justify="left").pack(padx=12, pady=8)
        self._scroll_bottom()

    def _card(self, title: str, accent: str) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self.chat, fg_color="transparent")
        row.pack(fill="x", pady=6, padx=8)
        card = ctk.CTkFrame(row, fg_color=CARD_BG, border_color=accent,
                            border_width=1, corner_radius=10)
        card.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(card, text=title, font=(FONT, 12, "bold"), text_color=TEXT,
                     wraplength=WRAP, justify="left").pack(anchor="w", padx=14, pady=(10, 6))
        return card

    def _buttons(self, card, ok_text, ok_color, ok_hover, on_ok, on_cancel, cancel_text="Cancel"):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6, 12))
        ok = ctk.CTkButton(row, text=ok_text, width=110, height=32, font=(FONT, 12, "bold"),
                           fg_color=ok_color, hover_color=ok_hover, corner_radius=6)
        cancel = ctk.CTkButton(row, text=cancel_text, width=90, height=32, font=(FONT, 12),
                               fg_color=BORDER, hover_color="#3f3f46", text_color=TEXT,
                               corner_radius=6)
        ok.pack(side="right")
        cancel.pack(side="right", padx=(0, 8))

        def finish(result_fn, label, color):
            ok.configure(state="disabled")
            cancel.configure(state="disabled")
            ctk.CTkLabel(row, text=label, font=(FONT, 11), text_color=color).pack(side="left")
            result_fn()

        ok.configure(command=lambda: finish(on_ok, "✓ Confirmed", GREEN))
        cancel.configure(command=lambda: finish(on_cancel, "✗ Cancelled", RED))

    def _wait(self, build) -> object:
        """Construye una tarjeta en el hilo de UI y bloquea el hilo del agente hasta la respuesta."""
        event, result = threading.Event(), [None]

        def done(value):
            result[0] = value
            event.set()

        self.root.after(0, lambda: build(done))
        self._set_status("Waiting for your answer...", AMBER)
        event.wait()
        self._set_status("Working...", AMBER)
        return result[0]

    # ── Interfaz AgentUI (llamada desde el hilo del agente) ──

    def clear(self):
        def _clear():
            self._hide_dropdown()
            for w in self.chat.winfo_children():
                w.destroy()
        self.root.after(0, _clear)

    def say(self, text: str):
        color = AMBER if text.startswith("⚠") else TEXT
        self.root.after(0, lambda: self._agent_bubble(text, color))

    def status(self, text: str):
        self._set_status(text, AMBER)

    def log(self, text: str):
        def _update():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _update)

    def _detail_box(self, card, detail: str):
        lines = detail.count("\n") + 1
        box = ctk.CTkTextbox(card, height=min(300, 18 * lines + 16), font=(MONO, 11),
                             fg_color=INPUT_BG, text_color=TEXT, border_color=BORDER,
                             border_width=1, corner_radius=6, wrap="none")
        box.insert("1.0", detail)
        box.configure(state="disabled")
        box.pack(fill="x", padx=14, pady=(0, 12))

    def show(self, title: str, detail: str):
        """Tarjeta informativa (tablas de análisis), sin botones."""
        def build():
            self._detail_box(self._card(title, BORDER), detail)
            self._scroll_bottom()
        self.root.after(0, build)

    def chart(self, spec: dict):
        """Tarjeta con la gráfica (valores al pasar el mouse) y botón para abrirla interactiva."""
        def build():
            card = self._card(spec['title'], BORDER)
            try:
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                from core import charts
                fig, artists = charts.mpl_figure(spec)
                canvas = FigureCanvasTkAgg(fig, master=card)
                canvas.draw()
                canvas.get_tk_widget().pack(fill="x", padx=14, pady=(0, 6))
                card._hover = charts.attach_hover(artists)      # referencia viva para el hover
            except Exception as e:
                ctk.CTkLabel(card, text=f"Chart not available: {e}", font=(FONT, 11),
                             text_color=MUTED).pack(anchor="w", padx=14)
            ctk.CTkButton(card, text="Open interactive ↗", width=150, height=28, font=(FONT, 11),
                          fg_color=BORDER, hover_color="#3f3f46", text_color=TEXT, corner_radius=6,
                          command=lambda: threading.Thread(target=self._open_chart, args=(spec,),
                                                           daemon=True).start()
                          ).pack(anchor="e", padx=14, pady=(0, 12))
            self._scroll_bottom()
        self.root.after(0, build)

    def _open_chart(self, spec: dict):
        try:
            from core import charts
            charts.open_interactive(spec, os.path.join(config.APP_HOME, "charts"))
        except Exception as e:
            self.log(f"⚠ Could not open the interactive chart: {e}")

    def approve(self, title: str, detail: str) -> bool:
        def build(done):
            card = self._card(title, AMBER)
            self._detail_box(card, detail)
            self._buttons(card, "Approve ✓", GREEN, GREEN_HOV,
                          lambda: done(True), lambda: done(False))
            self._scroll_bottom()
        return bool(self._wait(build))

    def confirm_send(self, title: str, detail: str, warning: str, ok: str, cancel: str) -> bool:
        """Tarjeta roja para acciones irreversibles (envío): aviso explícito y botón rojo."""
        def build(done):
            card = self._card(title, RED)
            self._detail_box(card, detail)
            ctk.CTkLabel(card, text=warning, font=(FONT, 12, "bold"), text_color=RED,
                         wraplength=WRAP, justify="left").pack(anchor="w", padx=14)
            self._buttons(card, ok, RED, RED_HOV, lambda: done(True), lambda: done(False),
                          cancel_text=cancel)
            self._scroll_bottom()
        return bool(self._wait(build))

    def pick_file(self, title: str):
        """Explorador de archivos Excel (hilo de UI); None si se cancela."""
        def build(done):
            path = filedialog.askopenfilename(
                parent=self.root, title=title,
                filetypes=[("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")])
            done(path or None)
        return self._wait(build)

    def decide(self, decision: Decision):
        def build(done):
            card = self._card(decision.question, BLUE)
            n_rows = len(decision.context.get('rows') or decision.options)
            body = ctk.CTkScrollableFrame(card, fg_color="transparent", height=min(260, 34 * n_rows))
            body.pack(fill="x", padx=10)
            if decision.context.get('rows'):          # una lista desplegable por fila → {fila: opción}
                skip = decision.context.get('skip', '—')
                vars_ = []
                for row in decision.context['rows']:
                    line = ctk.CTkFrame(body, fg_color="transparent")
                    line.pack(fill="x", pady=3)
                    ctk.CTkLabel(line, text=row['label'], font=(FONT, 11), text_color=TEXT, anchor="w",
                                 wraplength=230, justify="left").pack(side="left", fill="x", expand=True)
                    v = ctk.StringVar(value=row.get('default') or skip)
                    ctk.CTkOptionMenu(line, values=[skip] + decision.options, variable=v, width=210,
                                      font=(FONT, 11), fg_color=INPUT_BG, button_color=BORDER,
                                      dropdown_font=(FONT, 11)).pack(side="right")
                    vars_.append((row['label'], v))
                pick = lambda: {k: v.get() for k, v in vars_ if v.get() != skip}
            elif decision.multi:
                vars_ = []
                for opt in decision.options:
                    v = ctk.BooleanVar(value=opt in decision.preselected)
                    ctk.CTkCheckBox(body, text=opt, variable=v, font=(FONT, 12),
                                    text_color=TEXT, border_color=MUTED,
                                    fg_color=BLUE).pack(anchor="w", pady=3)
                    vars_.append((opt, v))
                pick = lambda: [o for o, v in vars_ if v.get()]
            else:
                var = ctk.StringVar(value=decision.options[0] if decision.options else "")
                for opt in decision.options:
                    ctk.CTkRadioButton(body, text=opt, variable=var, value=opt, font=(FONT, 12),
                                       text_color=TEXT, border_color=MUTED,
                                       fg_color=BLUE).pack(anchor="w", pady=3)
                pick = var.get
            self._buttons(card, "Confirm", BLUE, BLUE_HOV,
                          lambda: done(pick()), lambda: done(None))
            self._scroll_bottom()
        return self._wait(build)

    # ── Acciones ─────────────────────────────────────────────

    def _send(self):
        text = self.entry.get().strip()
        if not text or self.busy:
            return
        self.entry.delete(0, "end")
        self._hide_dropdown()
        self._user_bubble(text)
        self._run_agent(lambda: self.agent.handle(text))

    def _clear_chat(self):
        """Botón 🗑: limpia la conversación (pantalla + memoria del modelo); no toca horas ni historial."""
        if not self.busy:
            self._run_agent(self.agent.clear_chat)

    def _run_agent(self, fn):
        self._set_busy(True)

        def work():
            com = _com_init()   # Outlook/Excel COM desde un hilo que no es el principal
            try:
                fn()
            except Exception as e:      # p. ej. al retomar la sesión: nunca bloquea la app
                self.log(f"⚠ {e}")
            finally:
                if com:
                    com.CoUninitialize()
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=work, daemon=True).start()

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.entry.configure(state=state)
        self.btn_send.configure(state=state)
        self.btn_clear.configure(state=state)
        if busy:
            self._set_status("Working...", AMBER)
            self._hide_dropdown()
            self.lbl_hint.configure(text="")
        else:
            self._set_status("Ready", MUTED)
            self.entry.focus_set()
            self._refresh_suggestions()

    def _set_status(self, text: str, color: str = MUTED):
        self.root.after(0, lambda: self.lbl_status.configure(text=f"●  {text}", text_color=color))

    def _toggle_log(self):
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_box.pack(side="top", fill="x", pady=(0, 8))
            self.btn_log.configure(text="▾ Details")
        else:
            self.log_box.pack_forget()
            self.btn_log.configure(text="▸ Details")

    def _check_ollama(self):
        ok, msg = llm.check_ollama()
        color = GREEN if ok else RED
        self.root.after(0, lambda: self.lbl_model.configure(text_color=color))
        if not ok:
            self.say(f"⚠ {msg}")
        else:
            llm.warm_up()

    def _model_menu(self, event):
        menu = tk.Menu(self.root, tearoff=0, bg=CARD_BG, fg=TEXT, activebackground=BORDER,
                       activeforeground=TEXT, bd=0, font=(FONT, 10))
        current = llm.current_model()
        models = llm.list_models() or [current]
        if config.OLLAMA_MODEL not in models:
            models.insert(0, config.OLLAMA_MODEL)
        for name in models:
            label = f"{'✓' if name == current else '   '}  {name}"
            if name == config.OLLAMA_MODEL:
                label += "   (default)"
            menu.add_command(label=label, command=lambda n=name: self._set_model(n))
        menu.tk_popup(event.x_root, event.y_root)

    def _set_model(self, name: str):
        self.settings.model = "" if name == config.OLLAMA_MODEL else name
        self.settings.save()
        llm.set_model(self.settings.model)
        self.lbl_model.configure(text=f"●  {llm.current_model()}", text_color=MUTED)
        threading.Thread(target=self._check_ollama, daemon=True).start()

    # ── Ajustes ──────────────────────────────────────────────

    def _open_settings(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Settings")
        win.geometry("520x210")
        win.resizable(False, False)
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.after(100, win.grab_set)

        ctk.CTkLabel(win, text="Email (Outlook account)", font=(FONT, 12, "bold"),
                     text_color=TEXT).pack(anchor="w", padx=20, pady=(14, 4))
        email_var = ctk.StringVar(value=self.settings.email)
        ctk.CTkEntry(win, textvariable=email_var, height=34, font=(FONT, 11), text_color=TEXT,
                     fg_color=INPUT_BG, border_color=BORDER).pack(fill="x", padx=20)
        # Mis proyectos se arman en el chat; los archivos van a la carpeta de trabajo
        ctk.CTkLabel(win, text=f"Your projects are managed in the chat.\nFiles: {config.WORK_DIR}",
                     font=(FONT, 11), text_color=MUTED, justify="left").pack(anchor="w", padx=20, pady=(10, 0))

        def save():
            self.settings.email = email_var.get().strip()
            self.settings.save()
            win.destroy()

        ctk.CTkButton(win, text="Save", width=100, height=34, font=(FONT, 12, "bold"),
                      fg_color=GREEN, hover_color=GREEN_HOV, corner_radius=6,
                      command=save).pack(anchor="e", padx=20, pady=16)


def main():
    root = ctk.CTk()
    ChatApp(root)
    root.mainloop()
