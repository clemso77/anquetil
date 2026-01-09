"""
Backlight control module using lgpio for PWM control
"""

import lgpio
import config


class Backlight:
    """Controls the TFT backlight using PWM"""
    
    def __init__(self, gpio_handle, pin=config.GPIO_BL):
        """
        Initialize backlight control
        
        Args:
            gpio_handle: lgpio chip handle
            pin: GPIO pin number (BCM) for backlight control
        """
        self.handle = gpio_handle
        self.pin = pin
        self.is_on = True
        self.brightness = config.BACKLIGHT_DEFAULT_DUTY
        
        # Configure pin as output
        lgpio.gpio_claim_output(self.handle, self.pin)
        
        # Start PWM on the backlight pin
        self.set_brightness(self.brightness)
    
    def set_brightness(self, duty_cycle):
        """
        Set backlight brightness using PWM
        
        Args:
            duty_cycle: Brightness level (0-100%)
        """
        if duty_cycle < 0:
            duty_cycle = 0
        elif duty_cycle > 100:
            duty_cycle = 100
        
        self.brightness = duty_cycle
        
        if duty_cycle == 0:
            lgpio.gpio_write(self.handle, self.pin, 0)
        elif duty_cycle == 100:
            lgpio.gpio_write(self.handle, self.pin, 1)
        else:
            # Set PWM: frequency and duty cycle
            lgpio.tx_pwm(self.handle, self.pin, config.BACKLIGHT_PWM_FREQ, duty_cycle)
        
        self.is_on = duty_cycle > 0
    
    def on(self):
        """Turn backlight on at default brightness"""
        self.set_brightness(config.BACKLIGHT_DEFAULT_DUTY)
        self.is_on = True
    
    def off(self):
        """Turn backlight off"""
        self.set_brightness(0)
        self.is_on = False
    
    def toggle(self):
        """Toggle backlight on/off"""
        if self.is_on:
            self.off()
        else:
            self.on()
    
    def cleanup(self):
        """Cleanup GPIO resources"""
        lgpio.gpio_write(self.handle, self.pin, 0)
