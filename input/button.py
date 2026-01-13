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
        self.press_start_time = 0
        self.last_state = 1  # Pull-up, so high when not pressed
        
        # Configure pin as input with pull-up
        lgpio.gpio_claim_input(self.handle, self.pin, lgpio.SET_PULL_UP)
        
        # Callbacks for press events
        self.on_short_press = None
        self.on_long_press = None
    
    def _is_pressed(self):
        """Check if button is currently pressed (low = pressed with pull-up)"""
        return lgpio.gpio_read(self.handle, self.pin) == 0
    
    def update(self):
        """
        Update button state and trigger callbacks
        Should be called regularly from main loop
        
        Returns:
            'short', 'long', or None depending on press type detected
        """
        current_state = lgpio.gpio_read(self.handle, self.pin)
        current_time = time.time()
        
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
                    if self.on_long_press:
                        self.on_long_press()
                    return 'long'
                else:
                    # Short press
                    if self.on_short_press:
                        self.on_short_press()
                    return 'short'
        
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
            'short', 'long', or None if timeout
        """
        start_time = time.time()
        
        while True:
            result = self.update()
            if result:
                return result
            
            if timeout and (time.time() - start_time) > timeout:
                return None
            
            time.sleep(0.01)  # Small delay to prevent CPU spinning
    
    def reset_state(self):
        """Reset button state to initial values"""
        self.pressed = False
        self.press_start_time = 0
        self.last_state = lgpio.gpio_read(self.handle, self.pin)
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        pass  # lgpio cleanup handled by main gpio handle
