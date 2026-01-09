import time
import math
from typing import Callable, List, Dict, Any, Optional

from PIL import Image, ImageDraw, ImageFont, ImageSequence
import config


def load_bus_frames(path: str) -> List[Image.Image]:
    """
    Charge un PNG (1 frame) ou un GIF (plusieurs frames) en RGBA.
    """
    img = Image.open(path)
    frames = []
    try:
        # GIF animé → frames multiples
        for frame in ImageSequence.Iterator(img):
            frames.append(frame.convert("RGBA"))
    except Exception:
        frames = [img.convert("RGBA")]

    if not frames:
        frames = [img.convert("RGBA")]
    return frames


def draw_vertical_gradient(draw: ImageDraw.ImageDraw, w: int, h: int, top, bottom):
    for y in range(h):
        t = y / max(1, (h - 1))
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


class BusPage:
    """
    UNE SEULE PAGE: bus qui danse + 2 prochains passages.

    fetch_fn(stop_point_ref, limit=2) doit renvoyer une liste de dicts:
      - wait_minutes (int)
      - optionnel: destination, line, expected_departure_utc etc.
    """

    def __init__(
        self,
        stop_point_ref: str,
        fetch_fn: Callable[[str, int], List[Dict[str, Any]]],
        bus_image_path: str,
        title: str = "Prochains bus",
        fetch_ttl_seconds: int = 20,
        fps: int = 12,
    ):
        self.stop_point_ref = stop_point_ref
        self.fetch_fn = fetch_fn
        self.bus_image_path = bus_image_path
        self.title = title

        # animation
        self.fps = max(1, int(fps))
        self._start = time.time()

        # cache data API
        self.fetch_ttl_seconds = fetch_ttl_seconds
        self._last_fetch = 0.0
        self._cached_items: List[Dict[str, Any]] = []

        # frames bus
        self._bus_frames: Optional[List[Image.Image]] = None

        # fonts
        try:
            self.font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            self.font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        except (IOError, OSError):
            self.font_title = ImageFont.load_default()
            self.font_big = ImageFont.load_default()
            self.font_small = ImageFont.load_default()

    def _get_bus_frames(self) -> List[Image.Image]:
        if self._bus_frames is None:
            self._bus_frames = load_bus_frames(self.bus_image_path)
        return self._bus_frames

    def _get_next_items(self) -> List[Dict[str, Any]]:
        now = time.time()
        if self._cached_items and (now - self._last_fetch) < self.fetch_ttl_seconds:
            return self._cached_items

        try:
            items = self.fetch_fn(self.stop_point_ref, 2) or []
            out = []
            for it in items[:2]:
                out.append({
                    "wait_minutes": int(it.get("wait_minutes", 0)),
                    "destination": it.get("destination") or it.get("destination_ref") or "",
                    "line": it.get("line") or it.get("line_ref") or "",
                })
            self._cached_items = out
            self._last_fetch = now
            return out
        except Exception:
            # garde l'ancien cache si erreur réseau
            return self._cached_items

    def render(self) -> Image.Image:
        w, h = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT  # 240 x 280

        # --- fond
        img = Image.new("RGB", (w, h), (8, 10, 18))
        draw = ImageDraw.Draw(img)
        draw_vertical_gradient(draw, w, h, top=(16, 24, 48), bottom=(8, 10, 18))

        # --- header compact
        header_h = 44
        draw.rounded_rectangle([8, 8, w - 8, 8 + header_h], radius=14, fill=(255, 255, 255))
        draw.text((16, 16), self.title, fill=(20, 20, 40), font=self.font_title)

        # --- animation time
        t = time.time() - self._start

        # bus frame (GIF: change frame; PNG: toujours 0)
        frames = self._get_bus_frames()
        frame_index = int(t * self.fps) % len(frames)
        bus_src = frames[frame_index]

        # --- taille bus (centré, assez gros)
        # On vise ~120-140 px de large sur 240px
        target_w = int(w * 0.58)  # ~139
        ratio = target_w / bus_src.width
        target_h = int(bus_src.height * ratio)
        bus_scaled = bus_src.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

        # “danse” même si image statique (amplitude ajustée petit écran)
        bounce = int(7 * math.sin(t * 4.2))
        tilt = 5 * math.sin(t * 3.6 + 0.5)
        sway = int(5 * math.sin(t * 2.1))

        bus_rot = bus_scaled.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)

        # --- position bus (centré)
        bus_area_top = 8 + header_h + 10
        bus_area_bottom = h - 2 * 70 - 18  # on garde la place pour 2 cartes en bas
        bus_area_h = max(60, bus_area_bottom - bus_area_top)

        bus_x = (w - bus_rot.width) // 2 + sway
        bus_y = bus_area_top + (bus_area_h - bus_rot.height) // 2 + bounce

        # ombre sous le bus (discrète)
        shadow_w = int(target_w * 0.75)
        shadow_h = 14
        shadow_x = (w - shadow_w) // 2
        shadow_y = min(h - 160, bus_y + bus_rot.height + 6)
        draw.ellipse([shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h], fill=(0, 0, 0))

        # collage alpha
        base = img.convert("RGBA")
        base.alpha_composite(bus_rot, dest=(bus_x, bus_y))
        img = base.convert("RGB")
        draw = ImageDraw.Draw(img)

        # --- cartes prochains passages (pleine largeur)
        items = self._get_next_items()

        card_h = 64
        gap = 10
        left = 10
        right = w - 10
        bottom_margin = 10

        y2_card2 = h - bottom_margin
        y1_card2 = y2_card2 - card_h
        y2_card1 = y1_card2 - gap
        y1_card1 = y2_card1 - card_h

        cards = [(y1_card1, y2_card1), (y1_card2, y2_card2)]
        palettes = [
            {"bar": (60, 180, 255), "accent": (10, 70, 120)},
            {"bar": (255, 200, 80), "accent": (120, 70, 10)},
        ]

        for i, (y1, y2) in enumerate(cards):
            pal = palettes[i]

            # fond carte
            draw.rounded_rectangle([left, y1, right, y2], radius=16, fill=(255, 255, 255))
            # barre accent
            draw.rounded_rectangle([left, y1, left + 10, y2], radius=16, fill=pal["bar"])

            if i < len(items):
                wait = items[i].get("wait_minutes", 0)
                dest = items[i].get("destination", "")
                line = items[i].get("line", "")

                # gros minutes à gauche
                wait_txt = f"{wait} min"
                draw.text((left + 16, y1 + 10), wait_txt, fill=pal["accent"], font=self.font_big)

                # ligne/destination à droite (sur 1 ligne)
                meta = ""
                if line and dest:
                    meta = f"{line} → {dest}"
                elif dest:
                    meta = dest
                elif line:
                    meta = str(line)
                else:
                    meta = "Prochain passage"

                # petit texte sous les minutes
                draw.text((left + 16, y1 + 42), meta[:30], fill=(40, 40, 60), font=self.font_small)
            else:
                draw.text((left + 16, y1 + 10), "-- min", fill=(120, 120, 130), font=self.font_big)
                draw.text((left + 16, y1 + 42), "Données indisponibles", fill=(120, 120, 130), font=self.font_small)

        return img
