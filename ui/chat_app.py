# ============================================================
# CHAT — CustomTkinter / Zinc Dark Theme (misma paleta que Workday_Tool)
# La UI está en inglés; el agente responde en el idioma del usuario.
# El agente corre en un hilo; decide/approve bloquean ese hilo
# hasta que el usuario responde en la tarjeta (threading.Event).
# ============================================================
import threading
from tkinter import filedialog

import customtkinter as ctk

import config
from agent import llm
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
INPUT_BG   = "#18181b"
LOG_BG     = "#0d0d0d"
LOG_FG     = "#00ff88"

FONT       = "Segoe UI"
MONO       = "Consolas"
WRAP       = 470

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

WELCOME = ("Hi! Tell me what you need, for example:\n"
           "  • \"Fill Workday for October\"\n"
           "  • \"Submit N4W for the weeks of October\"\n"
           "  • \"Show me my hours for last month\"\n"
           "You can write in any language.")


class ChatApp:
    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("TimeSheet Agent")
        self.root.geometry("680x780")
        self.root.minsize(560, 600)
        self.root.configure(fg_color=BG)

        self.settings = Settings.load()
        self.agent = Agent(ui=self, settings=self.settings)
        self.busy = False
        self.log_visible = False

        self._build_ui()
        self._agent_bubble(WELCOME)
        threading.Thread(target=self._check_ollama, daemon=True).start()
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
        ctk.CTkLabel(left, text="Workday & N4W Facility assistant", font=(FONT, 11),
                     text_color=MUTED).pack(anchor="w")

        right = ctk.CTkFrame(hdr, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkButton(right, text="⚙", width=34, height=30, font=(FONT, 14),
                      fg_color=CARD_BG, hover_color=BORDER, border_color=BORDER,
                      border_width=1, corner_radius=6,
                      command=self._open_settings).pack(side="right", padx=(8, 0))
        self.lbl_model = ctk.CTkLabel(right, text=f"●  {config.OLLAMA_MODEL}",
                                      font=(FONT, 11), text_color=MUTED)
        self.lbl_model.pack(side="right")

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
        self.entry.bind("<Return>", lambda e: self._send())
        self.btn_send = ctk.CTkButton(bar, text="Send  ➤", width=90, height=40,
                                      font=(FONT, 12, "bold"), fg_color=BLUE,
                                      hover_color=BLUE_HOV, corner_radius=8, command=self._send)
        self.btn_send.pack(side="left")

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

    def _buttons(self, card, ok_text, ok_color, ok_hover, on_ok, on_cancel):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6, 12))
        ok = ctk.CTkButton(row, text=ok_text, width=110, height=32, font=(FONT, 12, "bold"),
                           fg_color=ok_color, hover_color=ok_hover, corner_radius=6)
        cancel = ctk.CTkButton(row, text="Cancel", width=90, height=32, font=(FONT, 12),
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

    def say(self, text: str):
        color = AMBER if text.startswith("⚠") else TEXT
        self.root.after(0, lambda: self._agent_bubble(text, color))

    def log(self, text: str):
        def _update():
            self.log_box.configure(state="normal")
            self.log_box.insert("end", text + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self.root.after(0, _update)

    def approve(self, title: str, detail: str) -> bool:
        def build(done):
            card = self._card(title, AMBER)
            lines = detail.count("\n") + 1
            box = ctk.CTkTextbox(card, height=min(260, 18 * lines + 16), font=(MONO, 11),
                                 fg_color=INPUT_BG, text_color=TEXT, border_color=BORDER,
                                 border_width=1, corner_radius=6, wrap="none")
            box.insert("1.0", detail)
            box.configure(state="disabled")
            box.pack(fill="x", padx=14)
            self._buttons(card, "Approve ✓", GREEN, GREEN_HOV,
                          lambda: done(True), lambda: done(False))
            self._scroll_bottom()
        return bool(self._wait(build))

    def decide(self, decision: Decision):
        def build(done):
            card = self._card(decision.question, BLUE)
            body = ctk.CTkScrollableFrame(card, fg_color="transparent",
                                          height=min(220, 30 * len(decision.options)))
            body.pack(fill="x", padx=10)
            if decision.multi:
                vars_ = []
                for opt in decision.options:
                    v = ctk.BooleanVar(value=False)
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
        self._user_bubble(text)
        self._set_busy(True)

        def work():
            try:
                self.agent.handle(text)
            finally:
                self.root.after(0, lambda: self._set_busy(False))

        threading.Thread(target=work, daemon=True).start()

    def _set_busy(self, busy: bool):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.entry.configure(state=state)
        self.btn_send.configure(state=state)
        if busy:
            self._set_status("Working...", AMBER)
        else:
            self._set_status("Ready", MUTED)
            self.entry.focus_set()

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

    # ── Ajustes ──────────────────────────────────────────────

    def _open_settings(self):
        win = ctk.CTkToplevel(self.root)
        win.title("Settings")
        win.geometry("520x250")
        win.resizable(False, False)
        win.configure(fg_color=BG)
        win.transient(self.root)
        win.after(100, win.grab_set)

        def field(label, value, browse=False):
            ctk.CTkLabel(win, text=label, font=(FONT, 12, "bold"),
                         text_color=TEXT).pack(anchor="w", padx=20, pady=(14, 4))
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=20)
            var = ctk.StringVar(value=value)
            ctk.CTkEntry(row, textvariable=var, height=34, font=(FONT, 11), text_color=TEXT,
                         fg_color=INPUT_BG, border_color=BORDER).pack(side="left", fill="x", expand=True)
            if browse:
                def pick():
                    path = filedialog.askopenfilename(
                        parent=win, title="Select projects database",
                        filetypes=[("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")])
                    if path:
                        var.set(path)
                ctk.CTkButton(row, text="Browse", width=80, height=34, font=(FONT, 11),
                              fg_color=BLUE, hover_color=BLUE_HOV, corner_radius=6,
                              command=pick).pack(side="left", padx=(8, 0))
            return var

        db_var = field("Projects database (Excel)", self.settings.db_path, browse=True)
        email_var = field("Email (Outlook account)", self.settings.email)

        def save():
            self.settings.db_path = db_var.get().strip()
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
