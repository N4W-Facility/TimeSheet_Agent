# ============================================================
# TRIBUTARY EN EL ESCRITORIO — ventana sin bordes, siempre encima, con fondo
# transparente (Windows: -transparentcolor): solo se ven el personaje y su burbuja.
# La usan la app minimizada (chat_app: "Sigo aquí para ayudarte") y el acompañante
# (companion.py: recordatorios con la app cerrada). Clic en Tributary → on_click;
# se arrastra a cualquier parte y recuerda dónde quedó (profile['floater_pos']);
# la burbuja queda visible hasta que el usuario hace clic, usa uno de sus botones
# (acciones: "Actualizar", "Más tarde", "Ver novedades"…) o ✕.
# ============================================================
import time
import tkinter as tk

from agent import i18n, suggest
from ui import winapi
from ui.avatar import Avatar, talk_rate

KEY = "#ff00fe"           # color que Windows vuelve transparente (no aparece en el personaje)
CARD_BG = "#111113"
BORDER = "#38bdf8"        # el borde "hablando" de las burbujas del chat
BLUE = "#3b82f6"          # botón principal (como en el chat)
TEXT = "#fafafa"
MUTED = "#a1a1aa"
FONT = "Segoe UI"
AVATAR_H = 130            # px lógicos
BUBBLE_W = 250
MARGIN = 16               # separación del borde de la pantalla
DRAG_PX = 4               # menos que esto es un clic, no un arrastre
POS_KEY = "floater_pos"


def reminder_text(reminder, lang: str) -> str:
    kw = dict(reminder.kw)
    if "month" in kw:
        name = suggest.month_name(kw["month"], lang)
        kw["month"] = name[:1].upper() + name[1:] if reminder.msg == "remind_prev_month" else name
    return i18n.tr(reminder.msg, lang, **kw)


class Floater:
    def __init__(self, master, scale: float = 1.0, store=None, title: str = winapi.FLOATER_TITLE):
        """store: objeto con get(key)/put(key, value) para recordar la posición (reminders.Seen).
        title: distinto de la ventana principal; el del acompañante, distinto del de la app."""
        self.store = store
        self.k = scale
        self.win = tk.Toplevel(master)
        self.win.title(title)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=KEY)
        try:
            self.win.attributes("-topmost", True)
            self.win.attributes("-transparentcolor", KEY)
        except tk.TclError:                       # fuera de Windows: fondo de color, sin transparencia
            pass

        self.bubble = tk.Canvas(self.win, bg=KEY, highlightthickness=0, bd=0)
        self.bubble.pack(side="top", anchor="e")
        self.avatar = Avatar(self.win, KEY, round(AVATAR_H * scale), cutout=True)
        self.avatar.canvas.pack(side="top", anchor="e")

        self._on_click = self._on_close = None
        self._actions = []
        self._shown = None                        # (texto, botones) dibujados
        self._text = ""
        self._typing = None
        self._press = None                        # (x, y del puntero, x, y de la ventana)
        self.visible = False
        for widget in (self.bubble, self.avatar.canvas):
            widget.bind("<ButtonPress-1>", self._press_start, add="+")
            widget.bind("<B1-Motion>", self._drag, add="+")
            widget.bind("<ButtonRelease-1>", self._release, add="+")
            widget.configure(cursor="hand2")

    # ── API ──────────────────────────────────────────────────

    def show(self, text: str, on_click, on_close=None, actions=()):
        """Aparece (o cambia lo que dice) y lo dice moviendo la boca.
        actions: [(texto, función, principal?)] → botones bajo el mensaje."""
        self._on_click = on_click
        self._on_close = on_close or self.hide
        self._actions = list(actions)
        appearing = not self.visible
        shown = (text, tuple((a[0], a[2]) for a in self._actions))
        if shown == self._shown and not appearing:
            return                                # ya lo está diciendo
        if shown != self._shown or appearing:
            self._text, self._shown = text, shown
            self._draw_bubble(text)
            self._place()
        if appearing:
            self.win.deiconify()
            self.win.lift()
            self.visible = True
            self.avatar.greet()
        self.avatar.speak(text)
        self._type(time.monotonic())

    def hide(self):
        if self._typing:
            self.win.after_cancel(self._typing)
            self._typing = None
        self.win.withdraw()
        self.visible = False
        self._text, self._shown = "", None

    def set_busy(self, busy: bool):
        self.avatar.set_busy(busy)

    def destroy(self):
        self.avatar.destroy()
        self.win.destroy()

    # ── Burbuja ──────────────────────────────────────────────

    def _draw_bubble(self, text: str):
        k, c = self.k, self.bubble
        c.delete("all")
        w, pad, r = round(BUBBLE_W * k), round(12 * k), round(12 * k)
        tail = round(14 * k)
        body = c.create_text(pad, pad, anchor="nw", text=text, fill=TEXT, width=w - 2 * pad - round(14 * k),
                             font=(FONT, 10))
        self._body = body
        h = c.bbox(body)[3] + pad
        if self._actions:
            h = self._draw_actions(h - round(2 * k), w - pad, pad) + pad
        # rectángulo redondeado + colita hacia la cabeza de Tributary (abajo a la derecha)
        tx = w - self.avatar.w // 2
        pts = [r, 0, w - r, 0, w, 0, w, r, w, h - r, w, h, w - r, h,
               tx + tail, h, tx + tail // 3, h + tail, tx - tail // 2, h,
               r, h, 0, h, 0, h - r, 0, r, 0, 0]
        shape = c.create_polygon(pts, smooth=True, fill=CARD_BG, outline=BORDER, width=max(1, round(k)))
        c.tag_lower(shape)
        close = c.create_text(w - pad, pad - round(4 * k), anchor="ne", text="✕", fill=MUTED,
                              font=(FONT, 10, "bold"), tags="close")
        c.tag_bind(close, "<ButtonRelease-1>", lambda e: self._on_close and self._on_close())
        c.configure(width=w + 2, height=h + tail + 2)

    def _draw_actions(self, top: int, right: int, left: int) -> int:
        """Botones bajo el mensaje (el principal relleno, el resto enlaces); pasan a otra línea
        si no caben. Devuelve dónde terminan."""
        k, c = self.k, self.bubble
        px, py = round(10 * k), round(4 * k)
        x, y, bottom = left, top, top
        for i, (label, fn, primary) in enumerate(self._actions):
            tag = f"action{i}"
            dx = px if primary else 0
            item = c.create_text(x + dx, y + py, anchor="nw", text=label, tags=(tag, "button"),
                                 fill=TEXT if primary else BORDER,
                                 font=(FONT, 9, "bold") if primary else (FONT, 9, "underline"))
            if c.bbox(item)[2] + dx > right and x > left:      # no cabe: a la línea siguiente
                c.move(item, left - x, bottom - y + round(6 * k))
                x, y = left, bottom + round(6 * k)
            x0, y0, x1, y1 = c.bbox(item)
            if primary:
                box = c.create_rectangle(x0 - px, y0 - py, x1 + px, y1 + py, fill=BLUE, outline=BLUE,
                                         tags=(tag, "button"))
                c.tag_lower(box, item)
                x1, y1 = x1 + px, y1 + py
            c.tag_bind(tag, "<ButtonRelease-1>", lambda e, f=fn: f and f())
            x, bottom = x1 + round(12 * k), max(bottom, y1)
        return bottom

    def _type(self, start: float):
        """La burbuja se escribe al ritmo de la boca (como en el chat)."""
        if self._typing:
            self.win.after_cancel(self._typing)
            self._typing = None
        text = self._text
        n = int((time.monotonic() - start) * talk_rate(len(text)))
        self.bubble.itemconfigure(self._body, text=text[:n] or "…")
        if n < len(text) and self.visible:
            self._typing = self.win.after(40, lambda: self._type(start))

    # ── Posición y arrastre ──────────────────────────────────

    def _anchor(self):
        """Esquina inferior derecha guardada, o la de la pantalla sobre la barra de tareas."""
        saved = self.store.get(POS_KEY) if self.store else ""
        vx0, vy0, vx1, vy1 = winapi.virtual_screen(self.win)
        try:
            x, y = (int(v) for v in saved.split(","))
            if vx0 + 80 <= x <= vx1 and vy0 + 80 <= y <= vy1:     # el monitor puede ya no estar
                return x, y
        except ValueError:
            pass
        _l, _t, right, bottom = winapi.work_area(self.win)
        return right - MARGIN, bottom - MARGIN

    def _place(self, anchor=None):
        self.win.update_idletasks()
        x, y = anchor or self._anchor()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        vx0, vy0, _vx1, _vy1 = winapi.virtual_screen(self.win)
        self.win.geometry(f"+{max(vx0, x - w)}+{max(vy0, y - h)}")

    def _press_start(self, event):
        self._press = (event.x_root, event.y_root, self.win.winfo_x(), self.win.winfo_y())

    def _drag(self, event):
        if not self._press:
            return
        px, py, wx, wy = self._press
        dx, dy = event.x_root - px, event.y_root - py
        if abs(dx) + abs(dy) >= DRAG_PX:
            self.win.geometry(f"+{wx + dx}+{wy + dy}")

    def _release(self, event):
        press, self._press = self._press, None
        if not press or self._on_button(event):
            return
        px, py, _wx, _wy = press
        if abs(event.x_root - px) + abs(event.y_root - py) >= DRAG_PX:       # arrastre: recordar
            if self.store:
                x = self.win.winfo_x() + self.win.winfo_width()
                y = self.win.winfo_y() + self.win.winfo_height()
                self.store.put(POS_KEY, f"{x},{y}")
            return
        if self._on_click:
            self._on_click()

    def _on_button(self, event) -> bool:
        """El clic cayó en un botón o ✕ (lo atiende su tag_bind): no cuenta también como "abrir"."""
        if event.widget is not self.bubble:
            return False
        tags = {t for i in self.bubble.find_withtag("current") for t in self.bubble.gettags(i)}
        return bool(tags & {"close", "button"})
