"""
ST7789 TFT Display Driver
Supports 240x280 pixel displays using SPI interface
"""

import spidev
import lgpio
import time
from PIL import Image
import config


class TFT:
    """ST7789 TFT display driver"""
    
    def __init__(self, gpio_handle, spi_bus=config.SPI_BUS, spi_device=config.SPI_DEVICE):
        """
        Initialize TFT display
        
        Args:
            gpio_handle: lgpio chip handle
            spi_bus: SPI bus number
            spi_device: SPI device number
        """
        self.handle = gpio_handle
        self.width = config.DISPLAY_WIDTH
        self.height = config.DISPLAY_HEIGHT
        self.offset_x = config.DISPLAY_OFFSET_X
        self.offset_y = config.DISPLAY_OFFSET_Y
        
        # Configure GPIO pins
        lgpio.gpio_claim_output(self.handle, config.GPIO_DC)
        lgpio.gpio_claim_output(self.handle, config.GPIO_RST)
        
        # Initialize SPI
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = config.SPI_SPEED
        self.spi.mode = 0  # SPI mode 0
        
        # Reset and initialize display
        self._reset()
        self._init_display()
    
    def _reset(self):
        """Hardware reset of the display"""
        lgpio.gpio_write(self.handle, config.GPIO_RST, 1)
        time.sleep(0.01)
        lgpio.gpio_write(self.handle, config.GPIO_RST, 0)
        time.sleep(0.01)
        lgpio.gpio_write(self.handle, config.GPIO_RST, 1)
        time.sleep(0.12)
    
    def _write_command(self, cmd):
        """
        Write a command byte to the display
        
        Args:
            cmd: Command byte
        """
        lgpio.gpio_write(self.handle, config.GPIO_DC, 0)  # Command mode
        self.spi.writebytes([cmd])
    
    def _write_data(self, data):
        """
        Write data to the display
        
        Args:
            data: Single byte or list of bytes
        """
        lgpio.gpio_write(self.handle, config.GPIO_DC, 1)  # Data mode
        if isinstance(data, int):
            self.spi.writebytes([data])
        else:
            self.spi.writebytes(data)
    
    def _init_display(self):
        """Initialize the ST7789 display with proper settings"""
        # Software reset
        self._write_command(config.ST7789_SWRESET)
        time.sleep(0.15)
        
        # Sleep out
        self._write_command(config.ST7789_SLPOUT)
        time.sleep(0.05)
        
        # Color mode - 16-bit color (RGB565)
        self._write_command(config.ST7789_COLMOD)
        self._write_data(0x55)  # 16-bit/pixel
        
        # Memory data access control (rotation)
        self._write_command(config.ST7789_MADCTL)
        self._write_data(config.DISPLAY_ROTATION)  # Default orientation
        
        # Invert display colors (fix inverted colors issue)
        self._write_command(config.ST7789_INVON)
        time.sleep(0.01)
        
        # Normal display mode
        self._write_command(config.ST7789_NORON)
        time.sleep(0.01)
        
        # Display on
        self._write_command(config.ST7789_DISPON)
        time.sleep(0.01)
    
    def _set_window(self, x0, y0, x1, y1):
        """
        Set the pixel address window for drawing
        
        Args:
            x0, y0: Start coordinates
            x1, y1: End coordinates
        """
        # Apply display offsets
        x0 += self.offset_x
        x1 += self.offset_x
        y0 += self.offset_y
        y1 += self.offset_y
        
        # Column address set
        self._write_command(config.ST7789_CASET)
        self._write_data([x0 >> 8, x0 & 0xFF, x1 >> 8, x1 & 0xFF])
        
        # Row address set
        self._write_command(config.ST7789_RASET)
        self._write_data([y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF])
        
        # Write to RAM
        self._write_command(config.ST7789_RAMWR)
    
    def display_image(self, image):
        """
        Display a PIL Image on the screen
        
        Args:
            image: PIL Image object (will be resized to display dimensions)
        """
        # Ensure image is the correct size and format
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height), Image.LANCZOS)
        
        # Convert to RGB if not already
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        # Convert to RGB565 format
        pixels = image.load()
        pixel_data = []
        
        for y in range(self.height):
            for x in range(self.width):
                r, g, b = pixels[x, y]
                # Convert to RGB565
                rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
                pixel_data.append(rgb565 >> 8)    # High byte
                pixel_data.append(rgb565 & 0xFF)  # Low byte
        
        # Set window to full screen
        self._set_window(0, 0, self.width - 1, self.height - 1)
        
        # Write pixel data in chunks to avoid buffer overflow
        chunk_size = 4096
        lgpio.gpio_write(self.handle, config.GPIO_DC, 1)  # Data mode
        for i in range(0, len(pixel_data), chunk_size):
            self.spi.writebytes(pixel_data[i:i + chunk_size])
    
    def fill(self, color):
        """
        Fill the entire display with a solid color
        
        Args:
            color: RGB tuple (r, g, b) with values 0-255
        """
        image = Image.new('RGB', (self.width, self.height), color)
        self.display_image(image)
    
    def clear(self):
        """Clear the display (fill with black)"""
        self.fill((0, 0, 0))
    
    def display_off(self):
        """
        Turn off the display completely using ST7789 command.
        This puts the display into sleep mode and turns off the display output.
        More power efficient than just showing black pixels.
        """
        # Turn off display
        self._write_command(config.ST7789_DISPOFF)
        time.sleep(0.01)
        # Enter sleep mode for additional power savings
        self._write_command(config.ST7789_SLPIN)
        time.sleep(0.12)
    
    def display_on(self):
        """
        Turn on the display using ST7789 command.
        This wakes the display from sleep mode and turns on the display output.
        """
        # Exit sleep mode
        self._write_command(config.ST7789_SLPOUT)
        time.sleep(0.12)
        # Turn on display
        self._write_command(config.ST7789_DISPON)
        time.sleep(0.01)
    
    def cleanup(self):
        """Cleanup resources"""
        self.spi.close()
