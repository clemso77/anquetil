"""
ST7789 TFT Display Driver
Supports 240x280 pixel displays using SPI interface
"""

import logging
import spidev
import lgpio
import time
from PIL import Image
import config


class TFT:
    """ST7789 TFT display driver (Raspberry Pi 5 / Raspberry Pi OS Lite focused)."""

    def __init__(
        self,
        gpio_handle,
        spi_bus=config.SPI_BUS,
        spi_device=config.SPI_DEVICE,
        spi_speed_hz=None,
        rotation=None,
        offset_x=None,
        offset_y=None,
        init_mode=None,
        enable_inversion=None,
    ):
        """
        Initialize TFT display

        Args:
            gpio_handle: lgpio chip handle
            spi_bus: SPI bus number
            spi_device: SPI device number
            spi_speed_hz: SPI clock speed in Hz
            rotation: ST7789 MADCTL value
            offset_x: display X offset
            offset_y: display Y offset
            init_mode: "fast" or "safe"
            enable_inversion: whether to send INVON during init
        """
        self.logger = logging.getLogger(__name__)
        self.handle = gpio_handle
        self.width = config.DISPLAY_WIDTH
        self.height = config.DISPLAY_HEIGHT
        self.offset_x = config.DISPLAY_OFFSET_X if offset_x is None else offset_x
        self.offset_y = config.DISPLAY_OFFSET_Y if offset_y is None else offset_y
        self.rotation = config.DISPLAY_ROTATION if rotation is None else rotation
        self.spi_speed_hz = config.SPI_SPEED if spi_speed_hz is None else spi_speed_hz
        self.init_mode = config.DISPLAY_INIT_MODE if init_mode is None else init_mode
        self.enable_inversion = (
            config.DISPLAY_ENABLE_INVERSION
            if enable_inversion is None
            else enable_inversion
        )
        self.write_chunk_size = max(256, int(config.SPI_WRITE_CHUNK_SIZE))

        if self.init_mode not in ("fast", "safe"):
            self.logger.warning(
                "Unknown init_mode='%s', falling back to 'safe'", self.init_mode
            )
            self.init_mode = "safe"

        # Configure GPIO pins
        lgpio.gpio_claim_output(self.handle, config.GPIO_DC)
        lgpio.gpio_claim_output(self.handle, config.GPIO_RST)

        # Initialize SPI
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = int(self.spi_speed_hz)
        self.spi.mode = int(config.SPI_MODE)
        self.spi.cshigh = bool(config.SPI_CSHIGH)

        self.logger.info(
            "SPI opened bus=%s device=%s speed=%sHz mode=%s cshigh=%s",
            spi_bus,
            spi_device,
            self.spi.max_speed_hz,
            self.spi.mode,
            self.spi.cshigh,
        )
        time.sleep(float(config.SPI_INIT_DELAY_SECONDS))

        # Reset and initialize display
        self._reset()
        self._init_display()

    def _timing_profile(self):
        """Return command delays for selected init profile."""
        if self.init_mode == "fast":
            return {
                "reset_high_before": 0.02,
                "reset_low": 0.02,
                "reset_high_after": 0.12,
                "after_swreset": 0.15,
                "after_slpout": 0.12,
                "after_colmod": 0.01,
                "after_madctl": 0.01,
                "after_display_on": 0.10,
            }

        # Safe profile for slower/unstable systems.
        return {
            "reset_high_before": 0.03,
            "reset_low": 0.03,
            "reset_high_after": 0.18,
            "after_swreset": 0.18,
            "after_slpout": 0.15,
            "after_colmod": 0.02,
            "after_madctl": 0.02,
            "after_display_on": 0.12,
        }

    def _reset(self):
        """Hardware reset of the display"""
        t = self._timing_profile()
        self.logger.debug("Reset: RST high")
        lgpio.gpio_write(self.handle, config.GPIO_RST, 1)
        time.sleep(t["reset_high_before"])
        self.logger.debug("Reset: RST low")
        lgpio.gpio_write(self.handle, config.GPIO_RST, 0)
        time.sleep(t["reset_low"])
        self.logger.debug("Reset: RST high (release)")
        lgpio.gpio_write(self.handle, config.GPIO_RST, 1)
        time.sleep(t["reset_high_after"])

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
        """Initialize ST7789 with robust, Pi OS Lite friendly sequence."""
        t = self._timing_profile()

        self.logger.info("ST7789 init: SWRESET")
        self._write_command(config.ST7789_SWRESET)
        time.sleep(t["after_swreset"])

        self.logger.info("ST7789 init: SLPOUT")
        self._write_command(config.ST7789_SLPOUT)
        time.sleep(t["after_slpout"])

        self.logger.info("ST7789 init: COLMOD=RGB565")
        self._write_command(config.ST7789_COLMOD)
        self._write_data(0x55)  # 16-bit/pixel
        time.sleep(t["after_colmod"])

        self.logger.info("ST7789 init: MADCTL=0x%02X", self.rotation)
        self._write_command(config.ST7789_MADCTL)
        self._write_data(self.rotation)
        time.sleep(t["after_madctl"])

        if self.enable_inversion:
            self.logger.info("ST7789 init: INVON")
            self._write_command(config.ST7789_INVON)
        else:
            self.logger.info("ST7789 init: INVOFF")
            self._write_command(config.ST7789_INVOFF)

        self.logger.info("ST7789 init: NORON")
        self._write_command(config.ST7789_NORON)

        self.logger.info("ST7789 init: DISPON")
        self._write_command(config.ST7789_DISPON)
        time.sleep(t["after_display_on"])
        self.logger.info("ST7789 init: complete")

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
        lgpio.gpio_write(self.handle, config.GPIO_DC, 1)  # Data mode for streaming

    @staticmethod
    def _rgb_to_rgb565_bytes(image):
        """Convert RGB PIL image to packed big-endian RGB565 bytes."""
        rgb = image.tobytes()
        rgb565 = bytearray((len(rgb) // 3) * 2)
        j = 0

        for i in range(0, len(rgb), 3):
            r = rgb[i]
            g = rgb[i + 1]
            b = rgb[i + 2]
            value = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            rgb565[j] = (value >> 8) & 0xFF
            rgb565[j + 1] = value & 0xFF
            j += 2

        return rgb565

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
        pixel_data = self._rgb_to_rgb565_bytes(image)

        # Set window to full screen
        self._set_window(0, 0, self.width - 1, self.height - 1)

        # Write pixel data in chunks to avoid buffer overflow
        for i in range(0, len(pixel_data), self.write_chunk_size):
            self.spi.writebytes(pixel_data[i:i + self.write_chunk_size])

    def fill(self, color):
        """
        Fill the entire display with a solid color

        Args:
            color: RGB tuple (r, g, b) with values 0-255
        """
        image = Image.new('RGB', (self.width, self.height), color)
        self.display_image(image)

    def diagnostic_test(self, delay_seconds=1.0):
        """
        Run a basic end-to-end display diagnostic: red -> green -> blue.

        Args:
            delay_seconds: Delay between color fills.
        """
        self.logger.info("Diagnostic test: red")
        self.fill((255, 0, 0))
        time.sleep(delay_seconds)

        self.logger.info("Diagnostic test: green")
        self.fill((0, 255, 0))
        time.sleep(delay_seconds)

        self.logger.info("Diagnostic test: blue")
        self.fill((0, 0, 255))
        time.sleep(delay_seconds)

    def clear(self):
        """Clear the display (fill with black)"""
        self.fill((0, 0, 0))

    def display_off(self):
        """
        Turn off the display completely using ST7789 command.
        This puts the display into sleep mode and turns off the display output.
        More power efficient than just showing black pixels.
        """
        self.logger.info("Display off: DISPOFF -> SLPIN")
        # Turn off display (brief delay for command processing)
        self._write_command(config.ST7789_DISPOFF)
        time.sleep(0.01)
        # Enter sleep mode (ST7789 datasheet requires 120ms)
        self._write_command(config.ST7789_SLPIN)
        time.sleep(0.12)

    def display_on(self):
        """
        Turn on the display using ST7789 command.
        This wakes the display from sleep mode and turns on the display output.
        """
        self.logger.info("Display on: SLPOUT -> DISPON")
        # Exit sleep mode (ST7789 datasheet requires 120ms for wake-up)
        self._write_command(config.ST7789_SLPOUT)
        time.sleep(0.12)
        # Turn on display (brief delay for command processing)
        self._write_command(config.ST7789_DISPON)
        time.sleep(0.01)

    def cleanup(self):
        """Cleanup resources"""
        self.spi.close()
