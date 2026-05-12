"""
Button input handler with short and long press detection
"""

import lgpio
import time
import config


class Button:
    """Handles button input with short/long press detection"""
    
    def __init__(self, gpio_handle, pin=config.GPIO_BUTTON):
        """
        Initialize button handler
        
        Args:
            gpio_handle: lgpio chip handle
            pin: GPIO pin number (BCM) for button
        """
        self.handle = gpio_handle
        self.pin = pin
        self.pressed = False
        self.press_start_time = 0.0
        self.last_state = 1  # Pull-up, so high when not pressed
        
        # Configure pin as input with pull-up
        lgpio.gpio_claim_input(self.handle, self.pin, lgpio.SET_PULL_UP)
        
        # Callbacks for press events
        self.on_short_press = None
        self.on_long_press = None
        self.on_double_press = None
        self.pending_short_press_time = None
    
    def _is_pressed(self):
        """Check if button is currently pressed (low = pressed with pull-up)"""
        return lgpio.gpio_read(self.handle, self.pin) == 0
    
    def update(self):
        """
        Update button state and trigger callbacks
        Should be called regularly from main loop
        
        Returns:
            'short', 'double', 'long', or None depending on press type detected
        """
        current_state = lgpio.gpio_read(self.handle, self.pin)
        current_time = time.monotonic()
        
        # Fire pending short press if no second click happened in time
        # Only fire when button is released to avoid triggering while a second press is in progress.
        if self.pending_short_press_time is not None and current_state == 1:
            elapsed_ms = (current_time - self.pending_short_press_time) * 1000
            if elapsed_ms >= config.BUTTON_DOUBLE_CLICK_MS:
                self.pending_short_press_time = None
                if self.on_short_press:
                    self.on_short_press()
                return 'short'

        # Detect button press (transition from high to low)
        if current_state == 0 and self.last_state == 1:
            # Button just pressed
            self.pressed = True
            self.press_start_time = current_time
            self.last_state = current_state
            return None
        
        # Detect button release (transition from low to high)
        elif current_state == 1 and self.last_state == 0:
            # Button just released
            self.last_state = current_state
            
            if self.pressed:
                press_duration = (current_time - self.press_start_time) * 1000  # ms
                self.pressed = False
                
                # Debounce check
                if press_duration < config.BUTTON_DEBOUNCE_MS:
                    return None
                
                # Determine press type
                if press_duration >= config.BUTTON_LONG_PRESS_MS:
                    # Long press
                    self.pending_short_press_time = None
                    if self.on_long_press:
                        self.on_long_press()
                    return 'long'
                else:
                    # Short press candidate (wait briefly to detect double click)
                    if self.pending_short_press_time is not None:
                        interval_ms = (current_time - self.pending_short_press_time) * 1000
                        if 0 <= interval_ms <= config.BUTTON_DOUBLE_CLICK_MS:
                            self.pending_short_press_time = None
                            if self.on_double_press:
                                self.on_double_press()
                            return 'double'

                    self.pending_short_press_time = current_time
                    return None
        
        else:
            # No state change
            self.last_state = current_state
        
        return None
    
    def wait_for_press(self, timeout=None):
        """
        Block until button is pressed or timeout occurs
        
        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)
        
        Returns:
            'short', 'double', 'long', or None if timeout
        """
        start_time = time.monotonic()
        
        while True:
            result = self.update()
            if result:
                return result
            
            if timeout and (time.monotonic() - start_time) > timeout:
                return None
            
            time.sleep(0.01)  # Small delay to prevent CPU spinning
    
    def reset_state(self):
        """
        Reset button state to initial values.
        
        This method should be called when you need to clear any pending button
        state and start fresh with a clean detection cycle. Typically used after
        long press detection or when changing application modes to ensure no
        stale button press data affects subsequent button detection.
        """
        self.pressed = False
        self.press_start_time = 0
        self.pending_short_press_time = None
        self.last_state = lgpio.gpio_read(self.handle, self.pin)
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        pass  # lgpio cleanup handled by main gpio handle
