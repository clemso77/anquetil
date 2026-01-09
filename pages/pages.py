"""
Pages Module

Defines the BusPage class for rendering bus waiting times with improved UI.
Now uses centralized data management without direct fetch calls.
"""

import time
import math
from typing import List, Optional
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageSequence
import config
from services import DataManager, DataState


def load_bus_frames(path: str) -> List[Image.Image]:
    """
    Load PNG (1 frame) or GIF (multiple frames) in RGBA format.
    
    Args:
        path: Path to image file
        
    Returns:
        List of Image frames
    """
    img = Image.open(path)
    frames = []
    try:
        # Animated GIF → multiple frames
        for frame in ImageSequence.Iterator(img):
            frames.append(frame.convert("RGBA"))
    except Exception:
        frames = [img.convert("RGBA")]

    if not frames:
        frames = [img.convert("RGBA")]
    return frames


def draw_vertical_gradient(draw: ImageDraw.ImageDraw, w: int, h: int, top, bottom):
    """
    Draw a vertical gradient from top to bottom.
    
    Args:
        draw: ImageDraw object
        w: Width in pixels
        h: Height in pixels
        top: Top color RGB tuple
        bottom: Bottom color RGB tuple
    """
    for y in range(h):
        t = y / max(1, (h - 1))
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


class BusPage:
    """
    Single page display: dancing bus + 2 next departures.
    
    Integrates with DataManager for state-aware rendering.
    Displays loading, error, and empty states appropriately.
    """

    def __init__(
        self,
        data_manager: DataManager,
        bus_image_path: str,
        title: str = "Prochains bus",
        fps: int = 12,
    ):
        """
        Initialize the bus page.
        
        Args:
            data_manager: DataManager instance for accessing data and state
            bus_image_path: Path to bus image (PNG or animated GIF)
            title: Page title
            fps: Frames per second for animation
        """
        self.data_manager = data_manager
        self.bus_image_path = bus_image_path
        self.title = title

        # Animation
        self.fps = max(1, int(fps))
        self._start = time.time()

        # Bus frames cache
        self._bus_frames: Optional[List[Image.Image]] = None

        # Fonts
        try:
            self.font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
            self.font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
            self.font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
            self.font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        except (IOError, OSError):
            self.font_title = ImageFont.load_default()
            self.font_big = ImageFont.load_default()
            self.font_small = ImageFont.load_default()
            self.font_tiny = ImageFont.load_default()

    def _get_bus_frames(self) -> List[Image.Image]:
        """Get cached bus frames, loading if necessary."""
        if self._bus_frames is None:
            self._bus_frames = load_bus_frames(self.bus_image_path)
        return self._bus_frames

    def _format_last_update(self) -> str:
        """
        Format the last update timestamp for display.
        
        Returns:
            Formatted string like "Updated: 14:23:05" or "Never updated"
        """
        last_update = self.data_manager.last_update
        if last_update is None:
            return "Never updated"
        return f"Updated: {last_update.strftime('%H:%M:%S')}"

    def _draw_loading_spinner(self, draw: ImageDraw.ImageDraw, x: int, y: int, size: int = 20):
        """
        Draw a simple rotating loading spinner.
        
        Args:
            draw: ImageDraw object
            x: Center x position
            y: Center y position
            size: Spinner size in pixels
        """
        t = time.time() - self._start
        angle = (t * 360) % 360
        
        # Draw rotating arc
        bbox = [x - size//2, y - size//2, x + size//2, y + size//2]
        draw.arc(bbox, start=angle, end=angle + 270, fill=(100, 150, 255), width=3)

    def render(self) -> Image.Image:
        """
        Render the complete page with current state.
        
        Returns:
            PIL Image ready for display
        """
        w, h = config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT  # 240 x 280

        # --- Background (light gradient)
        img = Image.new("RGB", (w, h), (245, 246, 250))
        draw = ImageDraw.Draw(img)
        draw_vertical_gradient(draw, w, h, top=(250, 250, 252), bottom=(236, 238, 244))

        # --- Header (with status indicator)
        header_y = 14
        header_h = 42
        draw.rounded_rectangle([10, header_y, w - 10, header_y + header_h], radius=14, fill=(255, 255, 255))
        draw.text((18, header_y + 10), self.title, fill=(25, 25, 35), font=self.font_title)

        # Get current state
        state = self.data_manager.state

        # Status indicator
        status_x = w - 25
        status_y = header_y + 21
        status_color = {
            DataState.IDLE: (180, 180, 190),
            DataState.LOADING: (100, 150, 255),
            DataState.SUCCESS: (80, 220, 140),
            DataState.ERROR: (255, 100, 100),
        }.get(state, (180, 180, 190))
        
        draw.ellipse([status_x - 5, status_y - 5, status_x + 5, status_y + 5], fill=status_color)

        # Show loading spinner if loading
        if state == DataState.LOADING:
            self._draw_loading_spinner(draw, status_x - 20, status_y, size=12)

        # --- Animation time
        t = time.time() - self._start

        # Bus frame (GIF: change frame; PNG: always 0)
        frames = self._get_bus_frames()
        frame_index = int(t * self.fps) % len(frames)
        bus_src = frames[frame_index]

        # --- Bus size (centered)
        target_w = int(w * 0.58)
        ratio = target_w / bus_src.width
        target_h = int(bus_src.height * ratio)
        bus_scaled = bus_src.resize((target_w, target_h), resample=Image.Resampling.LANCZOS)

        # "Dance" animation
        bounce = int(7 * math.sin(t * 4.2))
        tilt = 5 * math.sin(t * 3.6 + 0.5)
        sway = int(5 * math.sin(t * 2.1))
        bus_rot = bus_scaled.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)

        # --- Bus position (lowered)
        bus_area_top = header_y + header_h + 18
        bus_area_bottom = h - 2 * 68 - 22  
        bus_area_h = max(60, bus_area_bottom - bus_area_top)

        bus_x = (w - bus_rot.width) // 2 + sway
        bus_y = bus_area_top + (bus_area_h - bus_rot.height) // 2 + bounce

        # Shadow under bus (light gray, not black)
        shadow_w = int(target_w * 0.72)
        shadow_h = 14
        shadow_x = (w - shadow_w) // 2
        shadow_y = min(h - 162, bus_y + bus_rot.height + 6)
        draw.ellipse([shadow_x, shadow_y, shadow_x + shadow_w, shadow_y + shadow_h], fill=(210, 214, 224))

        # Alpha composite
        base = img.convert("RGBA")
        base.alpha_composite(bus_rot, dest=(bus_x, bus_y))
        img = base.convert("RGB")
        draw = ImageDraw.Draw(img)

        # --- Info bar (last update + auto-refresh)
        info_y = bus_area_bottom + 8
        last_update_text = self._format_last_update()
        draw.text((12, info_y), last_update_text, fill=(120, 120, 140), font=self.font_tiny)
        
        auto_refresh_text = f"Auto: {config.REFRESH_INTERVAL_SECONDS}s"
        draw.text((w - 70, info_y), auto_refresh_text, fill=(120, 120, 140), font=self.font_tiny)

        # --- Data cards
        items = self.data_manager.get_formatted_items(limit=2)

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

        # Card colors (yellow + green accents, darker cards)
        palettes = [
            {"card": (34, 34, 46), "bar": (255, 200, 60), "text": (255, 255, 255)},  # yellow
            {"card": (34, 34, 46), "bar": (80, 220, 140), "text": (255, 255, 255)},  # green
        ]

        # Handle different states
        if state == DataState.ERROR:
            # Show error message
            error_msg = self.data_manager.error_message or "Error loading data"
            for i, (y1, y2) in enumerate(cards):
                pal = palettes[i]
                draw.rounded_rectangle([left, y1, right, y2], radius=16, fill=(60, 40, 40))
                draw.rounded_rectangle([left, y1, left + 10, y2], radius=16, fill=(255, 100, 100))
                if i == 0:
                    draw.text((left + 18, y1 + 22), "ERROR", fill=(255, 150, 150), font=self.font_small)
        
        elif state == DataState.LOADING and not self.data_manager.has_data():
            # Initial loading state
            for i, (y1, y2) in enumerate(cards):
                pal = palettes[i]
                draw.rounded_rectangle([left, y1, right, y2], radius=16, fill=pal["card"])
                draw.rounded_rectangle([left, y1, left + 10, y2], radius=16, fill=pal["bar"])
                if i == 0:
                    draw.text((left + 18, y1 + 22), "Loading...", fill=pal["text"], font=self.font_small)
        
        elif not items and state != DataState.LOADING:
            # Empty state (no data available)
            for i, (y1, y2) in enumerate(cards):
                pal = palettes[i]
                draw.rounded_rectangle([left, y1, right, y2], radius=16, fill=pal["card"])
                draw.rounded_rectangle([left, y1, left + 10, y2], radius=16, fill=pal["bar"])
                if i == 0:
                    draw.text((left + 18, y1 + 22), "No data", fill=(160, 160, 170), font=self.font_small)
        
        else:
            # Display data cards
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
                    # No data for this slot
                    draw.text((left + 18, y1 + 18), "--", fill=(120, 120, 130), font=self.font_big)
                    draw.text((left + 60, y1 + 36), "min", fill=(120, 120, 130), font=self.font_small)

        return img
