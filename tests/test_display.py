import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import config
from pages.pages import BusPage
from services.data_manager import DataManager
from PIL import Image


class BusPageDisplayTests(unittest.TestCase):
    def _create_temp_bus_image(self) -> str:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            image = Image.new("RGBA", (64, 64), (255, 200, 0, 255))
            image.save(tmp.name, format="PNG")
            return tmp.name

    def test_render_returns_display_sized_rgb_image(self):
        bus_image_path = self._create_temp_bus_image()
        self.addCleanup(lambda: Path(bus_image_path).unlink(missing_ok=True))

        data_manager = DataManager()
        data_manager.set_success(
            [
                {
                    "expected_departure_utc": (
                        datetime.now(timezone.utc) + timedelta(minutes=5)
                    ).isoformat(),
                    "status": "onTime",
                }
            ]
        )

        page = BusPage(data_manager=data_manager, bus_image_path=bus_image_path, fps=12)
        result = page.render()

        self.assertEqual(result.size, (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))
        self.assertEqual(result.mode, "RGB")

    def test_render_loading_state_without_data(self):
        bus_image_path = self._create_temp_bus_image()
        self.addCleanup(lambda: Path(bus_image_path).unlink(missing_ok=True))

        data_manager = DataManager()
        data_manager.set_loading()

        page = BusPage(data_manager=data_manager, bus_image_path=bus_image_path, fps=12)
        result = page.render()

        self.assertEqual(result.size, (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))

    def test_render_with_missing_bus_image_falls_back(self):
        data_manager = DataManager()
        data_manager.set_loading()
        missing_path = str(Path(tempfile.gettempdir()) / "does-not-exist-bus-image.png")

        page = BusPage(
            data_manager=data_manager,
            bus_image_path=missing_path,
            fps=12,
        )
        result = page.render()

        self.assertEqual(result.size, (config.DISPLAY_WIDTH, config.DISPLAY_HEIGHT))


if __name__ == "__main__":
    unittest.main()
