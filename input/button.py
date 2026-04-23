"""
Button input handler with short and long press detection.
"""

import logging
import time

import lgpio
import config

logger = logging.getLogger(__name__)


class Button:
    """Handles button input with short/long press detection."""

    def __init__(self, gpio_handle, pin: int = config.GPIO_BUTTON):
        """
        Initialise the button handler.

        Args:
            gpio_handle: lgpio chip handle.
            pin: GPIO pin number (BCM numbering) for the button.
        """
        self.handle = gpio_handle
        self.pin = pin
        self.pressed = False
        self.press_start_time: float = 0.0
        self.last_state: int = 1  # Pull-up → high when not pressed

        # Configure pin as input with pull-up
        lgpio.gpio_claim_input(self.handle, self.pin, lgpio.SET_PULL_UP)

        # Callbacks for press events
        self.on_short_press = None
        self.on_long_press = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def is_pressed(self) -> bool:
        """Return ``True`` if the button is currently held down."""
        return lgpio.gpio_read(self.handle, self.pin) == 0

    # ------------------------------------------------------------------
    # Main update loop method
    # ------------------------------------------------------------------

    def update(self):
        """
        Poll the button state and fire callbacks on press/release.

        Must be called regularly from the main loop.

        Returns:
            ``'short'``, ``'long'``, or ``None`` depending on the press
            type detected on this call.
        """
        current_state = lgpio.gpio_read(self.handle, self.pin)
        current_time = time.time()

        if current_state == 0 and self.last_state == 1:
            # Falling edge — button just pressed
            self.pressed = True
            self.press_start_time = current_time
            self.last_state = current_state
            return None

        if current_state == 1 and self.last_state == 0:
            # Rising edge — button just released
            self.last_state = current_state

            if self.pressed:
                press_duration_ms = (current_time - self.press_start_time) * 1000
                self.pressed = False

                if press_duration_ms < config.BUTTON_DEBOUNCE_MS:
                    return None  # Ignore glitches

                if press_duration_ms >= config.BUTTON_LONG_PRESS_MS:
                    if self.on_long_press:
                        self.on_long_press()
                    return "long"
                else:
                    if self.on_short_press:
                        self.on_short_press()
                    return "short"

        else:
            self.last_state = current_state

        return None

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def reset_state(self):
        """
        Reset button state to initial values.

        Call this after handling a long press or changing application mode
        to ensure stale press data does not affect subsequent detection.
        """
        self.pressed = False
        self.press_start_time = 0.0
        self.last_state = lgpio.gpio_read(self.handle, self.pin)

    def cleanup(self):
        """Cleanup GPIO resources (GPIO handle managed externally)."""
        pass
