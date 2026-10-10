# ============================================================
# AVATAR — personaje animado que acompaña el chat (tk.Canvas + Pillow)
# Capas en ui/avatar/ (las genera avatar/build_avatar.py): poses completas +
# parches de ojos/boca/cara que se superponen como items del Canvas.
# Un solo bucle after() en el hilo de UI: flota, respira (luz del pecho),
# parpadea, mira (al chat, al pensar, de reojo), mueve la boca al hablar y cambia
# de pose según lo que hace el agente; en reposo sonríe, ladea la cabeza o bosteza.
# El chat llama busy/waiting/speak/listen/ack/greet desde el hilo de UI; el texto de
# la burbuja se escribe al mismo ritmo que la boca (talk_rate).
# ============================================================
import json
import math
import os
import random
import time
import tkinter as tk

from PIL import Image, ImageDraw, ImageFilter, ImageTk

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "avatar")
FRAME_MS = 33              # ~30 fps
CHARS_PER_S = 16           # ritmo de la boca (y del texto que se escribe)
MAX_TALK_S = 5.0           # textos largos: se aceleran para no hablar más de esto
SYLLABLE_S = 0.08          # la boca cambia de forma como mucho a este ritmo
LISTEN_S = 1.5             # sigue "escuchando" este tiempo tras la última tecla
NOD_S = 0.3
FADE_S = 0.18              # crossfade entre poses
FADE_LEVELS = 5
BOB_PX = 0.03              # amplitud de la flotación (fracción del alto)
BOB_S = 2.8                # periodo de la flotación
GLOW_S = 3.4               # periodo del "latido" de la luz del pecho
GLOW_LEVELS = 8
LEAN_PX = 0.025            # cuánto se inclina hacia el ratón (fracción del ancho)
LOOP_S = 0.3               # cuadros de saludo/celebración que se alternan
LOOPS = {"wave": ("wave", "wave2"), "celebrate": ("celebrate", "celebrate2")}
TILTS = ("tilt_l", "tilt_r")
GLANCES = ("look_r", "look_ur", "look_up")
TILT_GAP_S = 10.0          # ladea la cabeza al empezar a escribir, como mucho cada tanto
YAWN_AFTER_S = 90.0        # sin actividad este tiempo: bosteza (una vez)


def talk_rate(n: int) -> float:
    """Caracteres por segundo para decir un texto de n caracteres."""
    return max(CHARS_PER_S, n / MAX_TALK_S)


def mouth_for(ch: str):
    """Forma de la boca para una letra: vocales y labiales; lo demás, la de reposo."""
    c = ch.lower()
    if c in "aáàâã":
        return "mouth_wide"
    if c in "oóôõuúü":
        return "mouth_o"
    if c in "eéê":
        return "mouth_teeth"
    if c in "iíy":
        return "mouth_small"
    if c in "mbp":
        return "mouth_closed"
    if c in "fv":
        return "mouth_teeth"
    return None


def reaction(text: str):
    """(gesto, ánimo) según cómo empieza el mensaje del agente: ✓ celebra, ⚠ se preocupa."""
    text = text.lstrip()
    if text.startswith(("✓", "✅")):
        return "celebrate", "happy"
    if text.startswith("⚠"):
        return None, "worried"
    return None, None


class Avatar:
    def __init__(self, master, bg: str, height: int, cutout: bool = False):
        """cutout: bordes sin semitransparencias, para un fondo que Windows vuelve transparente
        (Tributary sobre el escritorio): sin reflejo, luz del pecho ni fundidos."""
        self.cutout = cutout
        with open(os.path.join(ASSETS, "layers.json"), encoding="utf-8") as f:
            meta = json.load(f)
        k = height / meta["size"][1]
        self.w, self.h = round(meta["size"][0] * k), height
        self.pad = round(self.h * 0.06)             # aire arriba y abajo para flotar
        self.canvas = tk.Canvas(master, width=self.w, height=self.h + 4 * self.pad, bg=bg,
                                highlightthickness=0, bd=0)

        def scaled(name, solid=False):
            im = Image.open(os.path.join(ASSETS, name)).convert("RGBA")
            im = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
            if solid:                               # la silueta; los parches de la cara caen sobre ella
                im.putalpha(im.getchannel("A").point(lambda v: 255 if v >= 128 else 0))
            return im

        self._poses = {name: scaled(file, cutout) for name, file in meta["poses"].items()}
        self._pose_zones = meta["pose_zones"]
        self._patches = {name: (ImageTk.PhotoImage(scaled(p["file"])),
                                (round(p["xy"][0] * k), round(p["xy"][1] * k)), p["zone"])
                         for name, p in meta["patches"].items()}
        self._photos = {}                           # (pose, nivel) → PhotoImage (Tk necesita la referencia)
        self._glow_xy = (round(meta["glow"][0] * k), round(meta["glow"][1] * k))
        self._glows = self._make_glows()
        self._shadows = self._make_shadows()

        c = self.canvas
        self._shadow = c.create_image(0, 0, anchor="center")
        self._pose_item = c.create_image(0, 0, anchor="nw")
        self._old_item = c.create_image(0, 0, anchor="nw", state="hidden")
        self._glow = c.create_image(0, 0, anchor="center")
        self._face = c.create_image(0, 0, anchor="nw", state="hidden")
        self._eyes = c.create_image(0, 0, anchor="nw", state="hidden")
        self._mouth = c.create_image(0, 0, anchor="nw", state="hidden")
        self._dots = c.create_text(0, 0, anchor="w", text="", fill="#7dd3fc",
                                   font=("Segoe UI", max(9, self.h // 14), "bold"))
        self._shown = {}                            # item → imagen visible (evita reconfigurar igual)

        self.busy = False
        self.waiting = False
        self._pose = None                           # cuadro dibujado (wave2, celebrate2…)
        self._base = None                           # pose lógica (wave, celebrate…)
        self._fade = None                           # (pose anterior, inicio)
        self._gesture = (None, 0.0)                 # (pose, hasta)
        self._mood = (None, 0.0)                    # (parche de cara, hasta)
        self._talk = ("", 0.0, 0.0)                 # (texto, inicio, hasta)
        self._blink_at = time.monotonic() + 1.5
        self._blink_start = 0.0
        self._double = False
        self._hop = 0.0
        self._lean = 0.0
        self._hover_until = 0.0
        self._listen_until = 0.0
        self._nods = []                             # inicios de cada asentimiento
        self._glance = (None, 0.0)                  # (mirada, hasta)
        now = time.monotonic()
        self._life_at = now + 4.0                   # próximo gesto espontáneo en reposo
        self._active = now                          # última actividad (para el bostezo)
        self._yawned = False
        self._tilt_ok = 0.0
        self._anchor = None                         # alto (en el canvas) de la burbuja que dice
        self._top = None                            # posición vertical actual (se desliza)
        self._job = None

        c.bind("<Enter>", self._on_enter)
        c.bind("<Button-1>", self._on_click)
        c.configure(cursor="hand2")
        self._tick()

    # ── Eventos del chat ─────────────────────────────────────

    def set_busy(self, busy: bool):
        self.busy = busy
        self._activity()

    def set_waiting(self, waiting: bool):
        self.waiting = waiting
        self._activity()

    def speak(self, text: str):
        now = self._activity()
        self._talk = (text, now, now + max(0.6, len(text) / talk_rate(len(text))))
        self._listen_until = 0.0
        gesture, mood = reaction(text)
        if gesture:
            self.gesture(gesture, 1.6)
            self._hop = now
        if mood:
            self.mood(mood, 4.0)

    def gesture(self, pose: str, seconds: float):
        self._gesture = (pose, time.monotonic() + seconds)

    def mood(self, name: str, seconds: float):
        self._mood = (name, time.monotonic() + seconds)

    def listen(self, key: str = ""):
        """El usuario escribe: se inclina hacia el campo de texto y asiente entre palabras."""
        now = self._activity()
        if now >= self._listen_until and now >= self._tilt_ok and not (self.busy or self.waiting):
            self.gesture(random.choice(TILTS), 1.4)   # "a ver, ¿qué me cuentas?"
            self._tilt_ok = now + TILT_GAP_S
        self._listen_until = now + LISTEN_S
        if key in (" ", "space") and (not self._nods or now - self._nods[-1] > 1.2):
            self._nods.append(now)

    def ack(self):
        """Mensaje enviado: "ajá" — asiente dos veces y sonríe antes de pensar."""
        now = self._activity()
        self._nods = [now, now + NOD_S]
        self._listen_until = 0.0
        self.gesture("idle", 0.7)
        self.mood("happy", 0.9)

    def point_at(self, y):
        """Desliza al avatar para que su cara quede a la altura `y` del canvas (None: abajo)."""
        self._anchor = y

    def greet(self):
        self.gesture("wave", 2.4)
        self.mood("happy", 2.4)

    def destroy(self):
        if self._job:
            self.canvas.after_cancel(self._job)
            self._job = None

    def _on_enter(self, _event):
        now = time.monotonic()
        if not self.busy and now > self._hover_until:
            self.mood("surprised", 0.8)
            self._hover_until = now + 5.0           # no repetir la sorpresa a cada pasada

    def _on_click(self, _event):
        self.gesture("wave", 1.6)
        self.mood("happy", 2.2)
        self._hop = self._activity()

    def _activity(self):
        now = time.monotonic()
        self._active = now
        self._yawned = False
        self._life_at = max(self._life_at, now + 4.0)
        return now

    # ── Imágenes precalculadas ───────────────────────────────

    def _photo(self, pose: str, level: int = FADE_LEVELS):
        key = (pose, level)
        if key not in self._photos:
            im = self._poses[pose]
            if level < FADE_LEVELS:
                im = im.copy()
                im.putalpha(im.getchannel("A").point(lambda v: v * level // FADE_LEVELS))
            self._photos[key] = ImageTk.PhotoImage(im)
        return self._photos[key]

    def _make_glows(self):
        r = max(8, self.w // 7)
        base = Image.new("RGBA", (2 * r, 2 * r))
        ImageDraw.Draw(base).ellipse((r // 2, r // 2, r * 3 // 2, r * 3 // 2), fill=(200, 245, 255, 255))
        base = base.filter(ImageFilter.GaussianBlur(r / 3))
        out = []
        for i in range(GLOW_LEVELS):
            im = base.copy()
            im.putalpha(base.getchannel("A").point(lambda v, f=i / (GLOW_LEVELS - 1): int(v * 0.55 * f)))
            out.append(ImageTk.PhotoImage(im))
        return out

    def _make_shadows(self):
        """Reflejo azul bajo el personaje: más chico y tenue cuanto más alto flota."""
        out = []
        for i in range(GLOW_LEVELS):
            f = 1 - 0.25 * i / (GLOW_LEVELS - 1)
            w, h = int(self.w * 0.5 * f), max(4, int(self.pad * 0.7 * f))
            im = Image.new("RGBA", (w + 2 * h, 3 * h))
            ImageDraw.Draw(im).ellipse((h, h, h + w, 2 * h), fill=(56, 189, 248, int(90 * f)))
            out.append(ImageTk.PhotoImage(im.filter(ImageFilter.GaussianBlur(h / 2))))
        return out

    # ── Bucle de animación ───────────────────────────────────

    def _tick(self):
        try:
            if self.canvas.winfo_ismapped():
                self._frame(time.monotonic())
            self._job = self.canvas.after(FRAME_MS, self._tick)
        except tk.TclError:                         # ventana cerrada
            self._job = None

    def _current_pose(self, now):
        pose, until = self._gesture
        if pose and now < until:
            return pose
        talking = now < self._talk[2]
        if self.waiting:
            return "point"
        if self.busy and not talking:               # con la mano en la barbilla no puede hablar
            return "think"
        return "idle"

    def _frame_of(self, pose, now):
        """Cuadro a dibujar: saludo y celebración alternan dos imágenes."""
        frames = [f for f in LOOPS.get(pose, (pose,)) if f in self._poses]
        return frames[int(now / LOOP_S) % len(frames)] if frames else pose

    def _idle_life(self, now, pose):
        """En reposo: mira de reojo, sonríe suave o, tras mucho rato, bosteza."""
        talking = now < self._talk[2]
        if pose != "idle" or talking or self.busy or self.waiting or now < self._listen_until:
            return
        if not self._yawned and now - self._active > YAWN_AFTER_S and "yawn" in self._poses:
            self._yawned = True
            self.gesture("yawn", 2.2)
            return
        if now < self._life_at:
            return
        self._life_at = now + random.uniform(4.0, 9.0)
        if random.random() < 0.55:
            self._glance = (random.choice(GLANCES), now + random.uniform(0.7, 1.4))
        elif "soft" in self._patches:
            self.mood("soft", random.uniform(2.5, 4.0))

    def _gaze(self, now, pose):
        """Hacia dónde mira: arriba si piensa, al chat si escucha/espera/empieza a hablar."""
        if pose == "think":
            name = "look_up"
        elif self.waiting or now < self._listen_until or now - self._talk[1] < 0.5:
            name = "look_r"
        else:
            name, until = self._glance
            if now >= until:
                return None
        return name if name in self._patches else None

    def _show(self, item, image, x=None, y=None):
        if image is None:
            if self._shown.get(item) is not None:
                self.canvas.itemconfigure(item, state="hidden")
                self._shown[item] = None
            return
        if self._shown.get(item) is not image:
            self.canvas.itemconfigure(item, image=image, state="normal")
            self._shown[item] = image
        if x is not None:
            self.canvas.coords(item, x, y)

    def _blink(self, now):
        """None, 'eyes_half' o 'eyes_closed'; a veces parpadea dos veces seguidas."""
        if now >= self._blink_at:
            self._blink_start = now
            self._double = random.random() < 0.2
            self._blink_at = now + random.uniform(2.5, 6.0)
        t = now - self._blink_start
        if self._double and t > 0.2:
            t -= 0.2
        if t < 0.05 or 0.13 <= t < 0.18:
            return "eyes_half"
        if t < 0.13:
            return "eyes_closed"
        return None

    def _mouth_shape(self, now):
        """Por "sílabas": cada SYLLABLE_S toma la primera vocal de los próximos caracteres."""
        text, start, until = self._talk
        if now >= until:
            return None
        n = int((now - start) // SYLLABLE_S)
        i = int(n * SYLLABLE_S * talk_rate(len(text)))
        for ch in text[i:i + 3]:
            shape = mouth_for(ch)
            if shape == "mouth_wide" and n % 3 == 2 and "mouth_smile" in self._patches:
                return "mouth_smile"                # varía la "a" para que no se vea repetida
            if shape in self._patches:
                return shape
        return None

    def _frame(self, now):
        base = self._current_pose(now)
        self._idle_life(now, base)
        base = self._current_pose(now)              # el bostezo pudo empezar ahora
        if base != self._base:                      # cambio de pose: crossfade
            if self._pose is not None and not self.cutout:
                self._fade = (self._pose, now)
            self._base = base
        pose = self._pose = self._frame_of(base, now)   # cuadros del mismo gesto: sin fundido

        # Movimiento: flotación + salto (clic/celebración) + inclinación hacia el ratón
        phase = math.sin(2 * math.pi * now / BOB_S)
        bob = phase * self.h * BOB_PX
        t = now - self._hop
        if t < 0.45:
            bob -= self.h * 0.08 * 4 * (t / 0.45) * (1 - t / 0.45)
        self._nods = [n for n in self._nods if now - n < NOD_S or n > now]
        for n in self._nods:
            if now >= n:
                bob += self.h * 0.02 * math.sin(math.pi * (now - n) / NOD_S)
        if now < self._listen_until:                # atenta: inclinada hacia el chat/campo de texto
            target = self.w * LEAN_PX * 2
        else:
            try:
                px = self.canvas.winfo_pointerx() - self.canvas.winfo_rootx() - self.w / 2
                target = max(-1.0, min(1.0, px / (self.w * 2))) * self.w * LEAN_PX
            except tk.TclError:
                target = 0.0
        self._lean += (target - self._lean) * 0.08
        x0 = round(self._lean)
        lowest = max(0, self.canvas.winfo_height() - (self.h + 4 * self.pad))
        target = lowest if self._anchor is None else \
            max(0.0, min(lowest, self._anchor - 2 * self.pad - self.h * 0.3))
        self._top = target if self._top is None else self._top + (target - self._top) * 0.12
        top = round(self._top)
        y0 = round(top + self.pad * 2 + bob)

        # Pose (la nueva abajo; la anterior encima, desvaneciéndose)
        self._show(self._pose_item, self._photo(pose), x0, y0)
        fading = False
        if self._fade:
            old, start = self._fade
            f = (now - start) / FADE_S
            if f < 1:
                level = max(1, round((1 - f) * FADE_LEVELS))
                self._show(self._old_item, self._photo(old, level), x0, y0)
                fading = True
            else:
                self._fade = None
        if not fading:
            self._show(self._old_item, None)

        # Cara: ánimo, parpadeo y boca (solo en las poses que los admiten)
        zones = [] if fading else self._pose_zones.get(pose, [])
        mood, until = self._mood
        mood = mood if "face" in zones and now < until else None
        eyes = None
        if "eyes" in zones:
            eyes = self._blink(now) or (None if mood else self._gaze(now, base))
        layers = ((self._face, mood),
                  (self._eyes, eyes),
                  (self._mouth, self._mouth_shape(now) if "mouth" in zones else None))
        for item, name in layers:
            if name:
                photo, (px_, py_), _zone = self._patches[name]
                self._show(item, photo, x0 + px_, y0 + py_)
            else:
                self._show(item, None)

        # Luz del pecho que late y reflejo bajo el cuerpo
        if self.cutout:
            return self._dots_frame(now, x0, y0)
        g = (math.sin(2 * math.pi * now / GLOW_S) + 1) / 2
        gx, gy = self._glow_xy
        self._show(self._glow, self._glows[round(g * (GLOW_LEVELS - 1))], x0 + gx, y0 + gy)
        lift = (phase + 1) / 2 if t >= 0.45 else 1.0
        self._show(self._shadow, self._shadows[round(lift * (GLOW_LEVELS - 1))],
                   self.w / 2, top + self.h + self.pad * 3)
        self._dots_frame(now, x0, y0)

    def _dots_frame(self, now, x0, y0):
        """Puntos suspensivos mientras piensa."""
        if self.busy and not self.waiting and now >= self._talk[2]:
            n = int(now * 3) % 4
            self.canvas.itemconfigure(self._dots, text="•" * n)
            self.canvas.coords(self._dots, x0 + self.w * 0.68, y0 + self.h * 0.12)
        else:
            self.canvas.itemconfigure(self._dots, text="")
