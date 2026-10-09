# ============================================================
# CAPAS DEL AVATAR (se corre una vez, en desarrollo; no se distribuye)
#   python avatar/build_avatar.py
# Lee las imágenes generadas por IA (misma pose, solo cambia la cara) y deja
# en app/ui/avatar/ las poses completas + parches de ojos/boca/cara alineados
# sobre la base. Las variantes vienen corridas/escaladas unos px: cada una se
# alinea por la cara (sin ojos ni boca) y se copia solo su zona con borde suave.
# ============================================================
import json
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "app", "ui", "avatar")
HEIGHT = 440                     # alto guardado (la app lo reduce al tamaño de pantalla)

POSES = {                        # pose → imagen completa (alineadas con la base)
    "idle": "Tributary",
    "wave": "Tributary_1",
    "wave2": "Tributary_1a",     # segundo cuadro del saludo (se alterna con wave)
    "think": "Tributary_2",      # mano en la barbilla: tapa la boca
    "celebrate": "Tributary_3",  # trae su propia cara
    "celebrate2": "Tributary_1b",
    "point": "Tributary_4",
    "tilt_l": "Tributary_5",     # cabeza ladeada: curiosidad mientras el usuario escribe
    "tilt_r": "Tributary_6",
    "yawn": "Tributary_7",       # tras un rato sin actividad
}
ALIGN_BODY = {"tilt_l", "tilt_r", "yawn"}   # vienen a otra escala: se alinean por el cuerpo
PATCHES = {                      # parche → (variante, zona)
    "eyes_closed": ("Tributary_B2", "eyes"),
    "eyes_half": ("Tributary_B3", "eyes"),
    "mouth_small": ("Tributary_B4", "mouth"),
    "mouth_wide": ("Tributary_B5", "mouth"),
    "mouth_o": ("Tributary_B6", "mouth"),
    "happy": ("Tributary_B7", "face"),
    "worried": ("Tributary_B8", "face"),
    "surprised": ("Tributary_B9", "face"),
    "soft": ("Tributary_8", "face"),            # sonrisa suave de reposo
    "look_r": ("Tributary_C3", "eyes"),         # mirada hacia el chat
    "look_ur": ("Tributary_C1", "eyes"),
    "look_up": ("Tributary_C2", "eyes"),        # pensando
    "mouth_closed": ("Tributary_C7", "mouth"),  # m/b/p
    "mouth_teeth": ("Tributary_C5", "mouth"),   # e/f/v
    "mouth_smile": ("Tributary_C6", "mouth"),
}
POSE_ZONES = {                   # qué parches admite cada pose
    "idle": ["eyes", "mouth", "face"],
    "wave": ["eyes", "mouth", "face"],
    "wave2": ["eyes", "mouth", "face"],
    "point": ["eyes", "mouth", "face"],
    "think": ["eyes"],
    "celebrate": [],
    "celebrate2": [],
    "tilt_l": [],                # la cabeza se movió: los parches no caen en su sitio
    "tilt_r": [],
    "yawn": [],
}

# Coordenadas en la base (1254×1254)
FACE = (440, 280, 860, 600)                       # ventana para alinear
BODY = (300, 650, 1000, 1150)                     # ventana para alinear poses con la cabeza movida
EYES = [(543, 413, 70, 62), (746, 455, 68, 58)]   # elipses (cx, cy, rx, ry), sin cejas
BROWS = [(545, 388, 84, 92), (750, 432, 76, 86)]  # ojos + cejas (las emociones mueven las cejas)
MOUTH = [(622, 518, 88, 58)]
ZONES = {"eyes": EYES, "mouth": MOUTH, "face": BROWS + MOUTH}


def load(name):
    return Image.open(os.path.join(HERE, name + ".png")).convert("RGBA")


def _edges(im, step=1):
    a = np.asarray(im).astype(np.float32)[::step, ::step]
    g = a[..., :3].mean(2) * a[..., 3] / 255
    gx, gy = np.zeros_like(g), np.zeros_like(g)
    gx[:, 1:-1] = g[:, 2:] - g[:, :-2]
    gy[1:-1] = g[2:] - g[:-2]
    e = np.hypot(gx, gy)
    for cx, cy, rx, ry in ZONES["face"]:          # sin rasgos: solo contorno, pelo y mejillas
        e[(cy - ry) // step:(cy + ry) // step, (cx - rx) // step:(cx + rx) // step] = 0
    return e


def _best_shift(ref, mov, box, center, radius, step):
    x0, y0, x1, y1 = (v // step for v in box)
    r = ref[y0:y1, x0:x1]
    r = (r - r.mean()) / (r.std() + 1e-6)
    best = (-9.0, 0, 0)
    cx, cy = center
    for dy in range(cy - radius, cy + radius + 1):
        for dx in range(cx - radius, cx + radius + 1):
            m = mov[y0 + dy:y1 + dy, x0 + dx:x1 + dx]
            s = float((r * (m - m.mean())).mean() / (m.std() + 1e-6))
            if s > best[0]:
                best = (s, dx, dy)
    return best


def align(base, var, box=FACE):
    """Escala + traslación que lleva la cara (o `box`) de `var` sobre la de la base."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    ref2, ref1 = _edges(base, 2), _edges(base)
    best = None
    for sc in np.arange(0.92, 1.081, 0.01):
        w, h = var.size
        canvas = Image.new("RGBA", (w, h))
        canvas.paste(var.resize((round(w * sc), round(h * sc)), Image.LANCZOS),
                     (round(cx - cx * sc), round(cy - cy * sc)))
        s, dx, dy = _best_shift(ref2, _edges(canvas, 2), box, (0, 0), 24, 2)   # grueso a media escala
        if best is None or s > best[0]:
            best = (s, canvas, dx * 2, dy * 2)
    _, canvas, dx, dy = best
    _, dx, dy = _best_shift(ref1, _edges(canvas), box, (dx, dy), 2, 1)          # fino a escala real
    out = Image.new("RGBA", canvas.size)
    out.paste(canvas, (-dx, -dy))
    return out


def patch(var, zone):
    """Zona de la variante (ya alineada) con borde suave; la piel alrededor coincide con la base."""
    mask = Image.new("L", var.size)
    d = ImageDraw.Draw(mask)
    for cx, cy, rx, ry in ZONES[zone]:
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(6))
    out = var.copy()
    out.putalpha(ImageChops.multiply(mask, var.getchannel("A")))
    return out


def fade_bottom(im, frac=0.06):
    """La cola toca el borde inferior de la imagen: se desvanece para que no quede un corte recto."""
    w, h = im.size
    _, _, _, y1 = im.getchannel("A").getbbox()
    n = int(h * frac)
    ramp = Image.linear_gradient("L").resize((w, n)).transpose(Image.FLIP_TOP_BOTTOM)
    fade = Image.new("L", (w, h), 255)
    fade.paste(ramp, (0, y1 - n))
    fade.paste(0, (0, y1, w, h))
    im.putalpha(ImageChops.multiply(im.getchannel("A"), fade))
    return im


def chest_light(im):
    """Punto más brillante bajo la cara: la luz del pecho que la app hace latir."""
    a = np.asarray(im.filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    lum = a[..., :3].mean(2) * a[..., 3] / 255
    lum[:im.height // 2] = 0
    y, x = np.unravel_index(lum.argmax(), lum.shape)
    return [int(x), int(y)]


def main():
    os.makedirs(OUT, exist_ok=True)
    base = load(POSES["idle"])
    poses = {name: fade_bottom(align(base, load(src), BODY) if name in ALIGN_BODY else load(src))
             for name, src in POSES.items()}

    # recorte común a todas las poses y factor de escala
    x0, y0, x1, y1 = poses["idle"].getchannel("A").getbbox()
    for im in poses.values():
        bx0, by0, bx1, by1 = im.getchannel("A").getbbox()
        x0, y0, x1, y1 = min(x0, bx0), min(y0, by0), max(x1, bx1), max(y1, by1)
    k = HEIGHT / (y1 - y0)
    size = (round((x1 - x0) * k), HEIGHT)

    def shrink(im):
        return im.crop((x0, y0, x1, y1)).resize(size, Image.LANCZOS)

    meta = {"size": list(size), "poses": {}, "patches": {}, "pose_zones": POSE_ZONES,
            "glow": chest_light(shrink(poses["idle"]))}
    for name, im in poses.items():
        shrink(im).save(os.path.join(OUT, f"pose_{name}.png"), optimize=True)
        meta["poses"][name] = f"pose_{name}.png"
        print("pose", name)

    for name, (src, zone) in PATCHES.items():
        p = shrink(patch(align(base, load(src)), zone))
        box = p.getchannel("A").getbbox()
        p.crop(box).save(os.path.join(OUT, f"{name}.png"), optimize=True)
        meta["patches"][name] = {"file": f"{name}.png", "zone": zone, "xy": list(box[:2])}
        print("patch", name, box)

    with open(os.path.join(OUT, "layers.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


if __name__ == "__main__":
    main()
