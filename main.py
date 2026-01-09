#!/usr/bin/env python3
"""
Main application for Raspberry Pi TFT Display
Affiche une seule page animée (bus qui danse + 2 prochains passages)
sur un écran ST7789 avec un bouton (short: refresh, long: backlight).
"""

import sys
import time
import signal
import lgpio

from data.bus_delay import get_waiting_times

# Import project modules
import config
from screen.tft import TFT
from screen.backlight import Backlight
from input.button import Button
from pages.pages import BusPage


class Application:
    """Main application class"""

    def __init__(self):
        self.running = False
        self.gpio_handle = None
        self.tft = None
        self.backlight = None
        self.button = None

        # UNE SEULE PAGE
        self.page = None

        # Timing refresh écran
        self.last_frame_ts = 0.1
        self.target_fps = 12  # animation fluide sans trop charger le CPU

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        print("\nShutdown signal received, cleaning up...")
        self.running = False

    def setup(self):
        """Initialize hardware and create the single page"""
        print("Initializing Raspberry Pi TFT Display...")

        try:
            print("Opening GPIO chip...")
            self.gpio_handle = lgpio.gpiochip_open(0)

            print("Initializing TFT display...")
            self.tft = TFT(self.gpio_handle)

            print("Initializing backlight...")
            self.backlight = Backlight(self.gpio_handle)

            print("Initializing button...")
            self.button = Button(self.gpio_handle)

            # callbacks bouton
            self.button.on_short_press = self._on_short_press
            self.button.on_long_press = self._on_long_press

            # Create the single page (IMPORTANT: on la garde en attribut)
            print("Creating BusPage...")
            self.page = BusPage(
                stop_point_ref="STIF:StopPoint:Q:29631:",
                fetch_fn=get_waiting_times,
                bus_image_path="assets/bus.gif",
                title="Prochains bus",
                fetch_ttl_seconds=80,
                fps=44,
            )

            print("Displaying initial frame...")
            self._update_display(force=True)

            print("Initialization complete!")
            print("Short press: Refresh now")
            print("Long press: Toggle backlight")
            print("Press Ctrl+C to exit")

        except Exception as e:
            print(f"Error during setup: {e}")
            self.cleanup()
            raise

    def _on_short_press(self):
        """Short press: refresh immédiat (utile si tu veux forcer un redraw)"""
        print("Short press detected - refresh")
        self._update_display(force=True)

    def _on_long_press(self):
        """Long press: toggle backlight"""
        print("Long press detected - toggling backlight")
        self.backlight.toggle()

    def _update_display(self, force: bool = False):
        """Render + display the single page"""
        if not self.page or not self.tft:
            return

        # throttle FPS
        now = time.time()
        min_dt = 1.0 / self.target_fps
        if not force and (now - self.last_frame_ts) < min_dt:
            return

        self.last_frame_ts = now

        try:
            image = self.page.render()
            self.tft.display_image(image)
        except Exception as e:
            print(f"Error updating display: {e}")

    def run(self):
        """Main application loop"""
        self.running = True

        try:
            while self.running:
                # Update button state
                self.button.update()

                # Update screen (animation)
                self._update_display(force=False)

                # Petit sleep pour éviter de saturer CPU (bouton + rendu)
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nKeyboard interrupt received")
        except Exception as e:
            print(f"Error in main loop: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources"""
        print("Cleaning up...")

        try:
            if self.tft:
                print("Clearing display...")
                self.tft.clear()
                self.tft.cleanup()
        except Exception as e:
            print(f"Error cleaning up TFT: {e}")

        try:
            if self.backlight:
                print("Turning off backlight...")
                self.backlight.off()
                self.backlight.cleanup()
        except Exception as e:
            print(f"Error cleaning up backlight: {e}")

        try:
            if self.button:
                self.button.cleanup()
        except Exception as e:
            print(f"Error cleaning up button: {e}")

        try:
            if self.gpio_handle:
                print("Closing GPIO chip...")
                lgpio.gpiochip_close(self.gpio_handle)
        except Exception as e:
            print(f"Error closing GPIO: {e}")

        print("Cleanup complete")


def main():
    """Main entry point"""
    try:
        import lgpio  # noqa
        import spidev  # noqa
        from PIL import Image  # noqa
    except ImportError as e:
        print("Error: Required system packages not installed")
        print("Please install: python3-lgpio python3-spidev python3-pil")
        print(f"Import error: {e}")
        sys.exit(1)

    app = Application()

    try:
        app.setup()
        app.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
