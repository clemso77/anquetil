#!/usr/bin/env python3
"""
Main application for Raspberry Pi TFT Display
Displays pages on a ST7789 TFT screen with button navigation
"""

import sys
import time
import signal
import lgpio

# Import project modules
import config
from screen.tft import TFT
from screen.backlight import Backlight
from input.button import Button
from pages import create_default_pages


class Application:
    """Main application class"""
    
    def __init__(self):
        """Initialize the application"""
        self.running = False
        self.gpio_handle = None
        self.tft = None
        self.backlight = None
        self.button = None
        self.page_manager = None
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print("\nShutdown signal received, cleaning up...")
        self.running = False
    
    def setup(self):
        """Initialize hardware and create pages"""
        print("Initializing Raspberry Pi TFT Display...")
        
        try:
            # Open GPIO chip
            print("Opening GPIO chip...")
            self.gpio_handle = lgpio.gpiochip_open(0)  # GPIO chip 0 for RPi 5
            
            # Initialize TFT display
            print("Initializing TFT display...")
            self.tft = TFT(self.gpio_handle)
            
            # Initialize backlight
            print("Initializing backlight...")
            self.backlight = Backlight(self.gpio_handle)
            
            # Initialize button
            print("Initializing button...")
            self.button = Button(self.gpio_handle)
            
            # Setup button callbacks
            self.button.on_short_press = self._on_short_press
            self.button.on_long_press = self._on_long_press
            
            # Create pages
            print("Creating pages...")
            self.page_manager = create_default_pages()
            
            # Display initial page
            print("Displaying initial page...")
            self._update_display()
            
            print("Initialization complete!")
            print("Short press: Change page")
            print("Long press: Toggle backlight")
            print("Press Ctrl+C to exit")
            
        except Exception as e:
            print(f"Error during setup: {e}")
            self.cleanup()
            raise
    
    def _on_short_press(self):
        """Handle short button press - change page"""
        print("Short press detected - changing page")
        self.page_manager.next_page()
        self._update_display()
    
    def _on_long_press(self):
        """Handle long button press - toggle backlight"""
        print("Long press detected - toggling backlight")
        self.backlight.toggle()
    
    def _update_display(self):
        """Update the display with current page"""
        try:
            page = self.page_manager.get_current_page()
            if page:
                print(f"Rendering page: {page.name}")
                image = page.render()
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
                
                # Small delay to prevent CPU spinning
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
    # Check if running on compatible system
    try:
        import lgpio
        import spidev
        from PIL import Image
    except ImportError as e:
        print("Error: Required system packages not installed")
        print("Please install: python3-lgpio python3-spidev python3-pil")
        print(f"Import error: {e}")
        sys.exit(1)
    
    # Create and run application
    app = Application()
    
    try:
        app.setup()
        app.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
