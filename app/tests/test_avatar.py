"""Tests del avatar: lógica pura y capas empaquetadas (sin abrir ventanas)."""
import json
import os
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import avatar  # noqa: E402


def test_mouth_follows_vowels():
    assert avatar.mouth_for("a") == "mouth_wide"
    assert avatar.mouth_for("Ó") == "mouth_o"
    assert avatar.mouth_for("í") == "mouth_small"
    assert avatar.mouth_for("t") is None
    assert avatar.mouth_for(" ") is None


def test_reaction_to_agent_messages():
    assert avatar.reaction("✓ Workday filled for October.") == ("celebrate", "happy")
    assert avatar.reaction("⚠ Error: no Outlook") == (None, "worried")
    assert avatar.reaction("Hi! Which month?") == (None, None)


def test_layers_exist_and_fit_the_canvas():
    with open(os.path.join(avatar.ASSETS, "layers.json"), encoding="utf-8") as f:
        meta = json.load(f)
    w, h = meta["size"]
    for file in meta["poses"].values():
        assert Image.open(os.path.join(avatar.ASSETS, file)).size == (w, h)
    for name, p in meta["patches"].items():
        im = Image.open(os.path.join(avatar.ASSETS, p["file"]))
        x, y = p["xy"]
        assert x + im.width <= w and y + im.height <= h, name
    zones = {p["zone"] for p in meta["patches"].values()}
    assert set(meta["pose_zones"]) == set(meta["poses"])
    assert all(set(z) <= zones for z in meta["pose_zones"].values())
    # la boca que usa el habla existe como parche
    assert {"mouth_wide", "mouth_o", "mouth_small", "eyes_closed", "eyes_half"} <= set(meta["patches"])


def test_long_texts_are_said_faster_but_short_ones_at_normal_pace():
    assert avatar.talk_rate(20) == avatar.CHARS_PER_S
    assert 400 / avatar.talk_rate(400) <= avatar.MAX_TALK_S
