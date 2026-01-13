#!/usr/bin/env python3
"""
Main application for Raspberry Pi TFT Display

Displays a single animated page (dancing bus + 2 next departures)
on an ST7789 screen with a button (short: refresh, long: dimming).

Refactored architecture:
- Network calls are in services/api_service.py
- Auto-refresh managed by services/refresh_manager.py (80s interval)
- Data state managed by services/data_manager.py
- Main only handles display and button events
- Wait times calculated dynamically from UTC on every render
"""

import sys
import time
import signal
import lgpio
from PIL import Image

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


class Application:
    """
    Main application class.
    
    Handles hardware initialization, display rendering, and event processing.
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
        self.last_frame_ts = 0.1
        self.target_fps = 12  # Smooth animation without overloading CPU

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        print("\nShutdown signal received, cleaning up...")
        self.running = False

    def _fetch_data(self):
        """
        Fetch bus data and update data manager.
        Called by refresh manager on schedule and manual refresh.
        """
        print("Fetching bus data...")
        self.data_manager.set_loading()
        
        try:
            # Fetch data from API service
            data = self.api_service.fetch_waiting_times(
                stop_point_ref=self.stop_point_ref,
                limit=2,
                timeout=15
            )
            
            # Update data manager with success
            self.data_manager.set_success(data)
            print(f"Data fetched successfully: {len(data)} items")
            print(f"{data}")
            
        except Exception as e:
            # Update data manager with error
            error_msg = str(e)
            self.data_manager.set_error(error_msg)
            print(f"Error fetching data: {error_msg}")

    def setup(self):
        """Initialize hardware and create the single page."""
        print("Initializing Raspberry Pi TFT Display...")
        print(f"Auto-refresh interval: {config.REFRESH_INTERVAL_SECONDS} seconds")

        try:
            print("Opening GPIO chip...")
            self.gpio_handle = lgpio.gpiochip_open(0)

            print("Initializing TFT display...")
            self.tft = TFT(self.gpio_handle)

            print("Initializing backlight...")
            self.backlight = Backlight(self.gpio_handle)

            print("Initializing button...")
            self.button = Button(self.gpio_handle)

            # Button callbacks
            self.button.on_short_press = self._on_short_press
            self.button.on_long_press = self._on_long_press

            # Create the single page (uses data manager, no fetch function)
            print("Creating BusPage...")
            self.page = BusPage(
                data_manager=self.data_manager,
                bus_image_path="assets/bus.gif",
                title="Prochains bus",
                fps=44,
            )

            # Setup refresh manager
            print("Setting up refresh manager...")
            self.refresh_manager.set_refresh_callback(self._fetch_data)
            
            # Start auto-refresh (will do immediate first fetch)
            self.refresh_manager.start(immediate_refresh=True)

            print("Displaying initial frame...")
            self._update_display(force=True)

            print("Initialization complete!")
            print("Short press: Manual refresh")
            print("Long press: Shut down screen")
            print("Any press when screen is off: Restore screen")
            print("Press Ctrl+C to exit")

        except Exception as e:
            print(f"Error during setup: {e}")
            self.cleanup()
            raise

    def _on_short_press(self):
        """
        Short press: trigger immediate manual refresh (only if screen is on).
        """
        # If callbacks are suppressed, do nothing
        if self.suppress_button_callbacks:
            return
            
        # If screen is off, do nothing (restoration handled in update loop)
        if not self.screen_on:
            return
            
        print("Short press detected - triggering manual refresh")
        
        if self.refresh_manager.is_refreshing():
            print("Refresh already in progress, ignoring...")
            return
        
        # Trigger immediate refresh
        self.refresh_manager.refresh_now()
        
        # Force display update to show loading state
        self._update_display(force=True)

    def _on_long_press(self):
        """Long press: shut down the screen."""
        # If callbacks are suppressed, do nothing
        if self.suppress_button_callbacks:
            return
            
        # If screen is off, do nothing (restoration handled in update loop)
        if not self.screen_on:
            return
            
        print("Long press detected - shutting down screen")
        self.screen_on = False
        # Turn off backlight first
        self.backlight.off()
        # Cleanup button state for clean detection on next press
        self.button.reset_state()
        # Clear display to black
        self.tft.clear()

    def _update_display(self, force: bool = False):
        """
        Render and display the page.
        
        Args:
            force: If True, bypass FPS throttling
        """
        if not self.page or not self.tft:
            return

        # Throttle FPS
        now = time.time()
        min_dt = 1.0 / self.target_fps
        if not force and (now - self.last_frame_ts) < min_dt:
            return

        self.last_frame_ts = now

        try:
            # Render base page
            image = self.page.render()
            self.tft.display_image(image)
        except Exception as e:
            print(f"Error updating display: {e}")

    def run(self):
        """Main application loop."""
        self.running = True

        try:
            while self.running:
                # Check if we need to restore the screen
                if not self.screen_on:
                    # Check for any button press (press down, not release)
                    # last_state == 1 means button was not pressed (pull-up: high = not pressed)
                    if self.button._is_pressed() and self.button.last_state == 1:
                        # Button is being pressed and was not pressed before
                        print("Button press detected - restoring screen")
                        self.screen_on = True
                        self.backlight.on()
                        # Force display update to show screen content immediately
                        self._update_display(force=True)
                        # Suppress callbacks for this button press to prevent unwanted actions
                        self.suppress_button_callbacks = True
                
                try:
                    # Update button state
                    self.button.update()
                finally:
                    # Always re-enable callbacks after button update if they were suppressed
                    if self.suppress_button_callbacks:
                        self.suppress_button_callbacks = False

                # Update screen (animation) - only when screen is on
                if self.screen_on:
                    self._update_display(force=False)

                # Small sleep to avoid saturating CPU
                time.sleep(0.01)

        except KeyboardInterrupt:
            print("\nKeyboard interrupt received")
        except Exception as e:
            print(f"Error in main loop: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        """Cleanup resources."""
        print("Cleaning up...")

        # Stop refresh manager first
        try:
            if self.refresh_manager:
                self.refresh_manager.stop()
        except Exception as e:
            print(f"Error stopping refresh manager: {e}")

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
    """Main entry point - only handles initialization and display."""
    try:
        import lgpio  # noqa
        import spidev  # noqa
        # PIL Image already imported at module level
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
