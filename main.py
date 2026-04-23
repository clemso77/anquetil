#!/usr/bin/env python3
"""
Main application for Raspberry Pi TFT Display

Displays a single animated page (dancing bus + 2 next departures)
on an ST7789 screen with a button (short: refresh, long: screen off).

Architecture:
- Network calls are in services/api_service.py
- Auto-refresh managed by services/refresh_manager.py (80s interval)
- Data state managed by services/data_manager.py
- Main only handles display and button events
- Wait times calculated dynamically from UTC on every render
"""

import logging
import sys
import time
import signal

# Import configuration
import config

# Import hardware modules
from screen.tft import TFT
from screen.backlight import Backlight
from input.button import Button

# Import page
from pages.pages import BusPage

# Import services
from services import (
    get_api_service,
    get_data_manager,
    get_refresh_manager,
    DataState,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


class Application:
    """
    Main application class.

    Handles hardware initialisation, display rendering, and event processing.
    Data fetching and refresh management are delegated to services.
    """

    def __init__(self):
        self.running = False
        self.gpio_handle = None
        self.tft = None
        self.backlight = None
        self.button = None
        self.page = None

        # Screen state
        self.screen_on = True
        self.suppress_button_callbacks = False

        # Stop point reference for bus data
        self.stop_point_ref = config.BUS_ID

        # Services
        self.api_service = get_api_service()
        self.data_manager = get_data_manager()
        self.refresh_manager = get_refresh_manager(config.REFRESH_INTERVAL_SECONDS)

        # Display timing
        self.last_frame_ts: float = 0.0
        self.target_fps = 12  # Smooth animation without overloading CPU

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info("Shutdown signal received (%s), cleaning up...", signum)
        self.running = False

    def _fetch_data(self):
        """
        Fetch bus data and update the data manager.

        Called by the refresh manager on schedule and on manual refresh.
        """
        logger.info("Fetching bus data...")
        self.data_manager.set_loading()

        try:
            data = self.api_service.fetch_waiting_times(
                stop_point_ref=self.stop_point_ref,
                limit=2,
                timeout=15,
            )
            self.data_manager.set_success(data)
            logger.info("Data fetched successfully: %d item(s) — %s", len(data), data)
        except Exception:
            logger.exception("Error fetching bus data")
            self.data_manager.set_error("Network error — see logs for details")

    def setup(self):
        """Initialise hardware and create the single page."""
        logger.info("Initialising Raspberry Pi TFT Display...")
        logger.info("Auto-refresh interval: %ss", config.REFRESH_INTERVAL_SECONDS)

        try:
            logger.info("Opening GPIO chip...")
            import lgpio
            self.gpio_handle = lgpio.gpiochip_open(0)

            logger.info("Initialising TFT display...")
            self.tft = TFT(self.gpio_handle)

            logger.info("Initialising backlight...")
            self.backlight = Backlight(self.gpio_handle)

            logger.info("Initialising button...")
            self.button = Button(self.gpio_handle)
            self.button.on_short_press = self._on_short_press
            self.button.on_long_press = self._on_long_press

            logger.info("Creating BusPage...")
            self.page = BusPage(
                data_manager=self.data_manager,
                bus_image_path="assets/bus.gif",
                title="Prochains bus",
                fps=44,
            )

            logger.info("Setting up refresh manager...")
            self.refresh_manager.set_refresh_callback(self._fetch_data)
            self.refresh_manager.start(immediate_refresh=True)

            logger.info("Displaying initial frame...")
            self._update_display(force=True)

            logger.info("Initialisation complete!")
            logger.info("Short press: manual refresh | Long press: screen off | Ctrl+C: exit")

        except Exception:
            logger.exception("Error during setup")
            self.cleanup()
            raise

    def _on_short_press(self):
        """Short press: trigger immediate manual refresh (only if screen is on)."""
        if self.suppress_button_callbacks or not self.screen_on:
            return

        logger.info("Short press — triggering manual refresh")

        if self.refresh_manager.is_refreshing():
            logger.info("Refresh already in progress, ignoring")
            return

        self.refresh_manager.refresh_now()
        self._update_display(force=True)

    def _on_long_press(self):
        """Long press: shut down the screen completely."""
        if self.suppress_button_callbacks or not self.screen_on:
            return

        logger.info("Long press — shutting down screen")
        self.screen_on = False
        self.backlight.off()
        self.button.reset_state()
        self.tft.display_off()

    def _update_display(self, force: bool = False):
        """
        Render and push the current page to the display.

        Args:
            force: If ``True``, bypass FPS throttling.
        """
        if not self.page or not self.tft:
            return

        now = time.time()
        if not force and (now - self.last_frame_ts) < (1.0 / self.target_fps):
            return

        self.last_frame_ts = now

        try:
            image = self.page.render()
            self.tft.display_image(image)
        except Exception:
            logger.exception("Error updating display")

    def run(self):
        """Main application loop."""
        self.running = True

        try:
            while self.running:
                if not self.screen_on:
                    # Detect any press-down to restore the screen
                    if self.button.is_pressed() and self.button.last_state == 1:
                        logger.info("Button press — restoring screen")
                        self.screen_on = True
                        self.tft.display_on()
                        self.backlight.on()
                        self._update_display(force=True)
                        self.suppress_button_callbacks = True

                try:
                    self.button.update()
                finally:
                    if self.suppress_button_callbacks:
                        self.suppress_button_callbacks = False

                if self.screen_on:
                    self._update_display(force=False)

                time.sleep(0.01)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
        except Exception:
            logger.exception("Unexpected error in main loop")
        finally:
            self.cleanup()

    def cleanup(self):
        """Release all hardware resources."""
        logger.info("Cleaning up...")

        try:
            if self.refresh_manager:
                self.refresh_manager.stop()
        except Exception:
            logger.exception("Error stopping refresh manager")

        try:
            if self.api_service:
                self.api_service.close()
        except Exception:
            logger.exception("Error closing API service")

        try:
            if self.tft:
                logger.info("Turning off display...")
                self.tft.display_off()
                self.tft.cleanup()
        except Exception:
            logger.exception("Error cleaning up TFT")

        try:
            if self.backlight:
                logger.info("Turning off backlight...")
                self.backlight.off()
                self.backlight.cleanup()
        except Exception:
            logger.exception("Error cleaning up backlight")

        try:
            if self.button:
                self.button.cleanup()
        except Exception:
            logger.exception("Error cleaning up button")

        try:
            if self.gpio_handle is not None:
                logger.info("Closing GPIO chip...")
                import lgpio
                lgpio.gpiochip_close(self.gpio_handle)
                self.gpio_handle = None
        except Exception:
            logger.exception("Error closing GPIO")

        logger.info("Cleanup complete")


def main():
    """Application entry point."""
    try:
        import lgpio  # noqa: F401
        import spidev  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError as exc:
        print(
            "Error: required system packages are not installed.\n"
            "Please run: sudo apt install python3-lgpio python3-spidev python3-pil\n"
            f"Import error: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    app = Application()
    try:
        app.setup()
        app.run()
    except Exception:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    main()
