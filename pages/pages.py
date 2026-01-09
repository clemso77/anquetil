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

        # --- fond (clair)
        img = Image.new("RGB", (w, h), (245, 246, 250))
        draw = ImageDraw.Draw(img)
        # petit gradient très léger
        draw_vertical_gradient(draw, w, h, top=(250, 250, 252), bottom=(236, 238, 244))

        # --- header (descendu + sobre)
        header_y = 14  # DESCEND un peu
        header_h = 42
        draw.rounded_rectangle([10, header_y, w - 10, header_y + header_h], radius=14, fill=(255, 255, 255))
        draw.text((18, header_y + 10), self.title, fill=(25, 25, 35), font=self.font_title)

        # --- animation time
        t = time.time() - self._start

        # bus frame (GIF: change frame; PNG: toujours 0)
        frames = self._get_bus_frames()
        frame_index = int(t * self.fps) % len(frames)
        bus_src = frames[frame_index]

        # --- taille bus (centré)
        target_w = int(w * 0.58)
        ratio = target_w / bus_src.width
        target_h = int(bus_src.height * ratio)
        bus_scaled = bus_src.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

        # “danse”
        bounce = int(7 * math.sin(t * 4.2))
        tilt = 5 * math.sin(t * 3.6 + 0.5)
        sway = int(5 * math.sin(t * 2.1))
        bus_rot = bus_scaled.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)

        # --- position bus (DESCENDU)
        bus_area_top = header_y + header_h + 18
        bus_area_bottom = h - 2 * 68 - 22  
        bus_area_h = max(60, bus_area_bottom - bus_area_top)

        bus_x = (w - bus_rot.width) // 2 + sway
        bus_y = bus_area_top + (bus_area_h - bus_rot.height) // 2 + bounce

        # ombre sous le bus (gris clair, pas noir)
        shadow_w = int(target_w * 0.72)
        shadow_h = 14
        shadow_x = (w - shadow_w) // 2
        shadow_y = min(h - 162, bus_y + bus_rot.height + 6)
        draw.ellipse([shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h], fill=(210, 214, 224))

        # collage alpha
        base = img.convert("RGBA")
        base.alpha_composite(bus_rot, dest=(bus_x, bus_y))
        img = base.convert("RGB")
        draw = ImageDraw.Draw(img)

        items = self._get_next_items()

        card_h = 66
        gap = 10
        left = 12
        right = w - 12
        bottom_margin = 12

        y2_card2 = h - bottom_margin
        y1_card2 = y2_card2 - card_h
        y2_card1 = y1_card2 - gap
        y1_card1 = y2_card1 - card_h

        cards = [(y1_card1, y2_card1), (y1_card2, y2_card2)]

        # Couleurs "corrigées" : jaune + vert (accents), cartes plus sombres
        palettes = [
            {"card": (34, 34, 46), "bar": (255, 200, 60), "text": (255, 255, 255)},  # jaune
            {"card": (34, 34, 46), "bar": (80, 220, 140), "text": (255, 255, 255)},  # vert
        ]

        for i, (y1, y2) in enumerate(cards):
            pal = palettes[i]

            draw.rounded_rectangle([left, y1, right, y2], radius=16, fill=pal["card"])
            draw.rounded_rectangle([left, y1, left + 10, y2], radius=16, fill=pal["bar"])

            if i < len(items):
                wait = int(items[i].get("wait_minutes", 0))

                wait_txt = f"{wait}"
                bbox = draw.textbbox((0, 0), wait_txt, font=self.font_big)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                x = left + 18
                y = y1 + (card_h - th) // 2 - 2

                draw.text((x, y), wait_txt, fill=pal["text"], font=self.font_big)

                min_txt = "min"
                bbox2 = draw.textbbox((0, 0), min_txt, font=self.font_small)
                draw.text((x + tw + 8, y + th - (bbox2[3] - bbox2[1]) - 2), min_txt, fill=pal["text"], font=self.font_small)

            else:
                # fallback
                draw.text((left + 18, y1 + 18), "--", fill=(220, 220, 230), font=self.font_big)
                draw.text((left + 60, y1 + 36), "min", fill=(220, 220, 230), font=self.font_small)

        return img
