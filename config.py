"""
Configuration file for Raspberry Pi TFT Display Project
All GPIO pins use BCM numbering
"""

# GPIO Pin Configuration (BCM numbering)
GPIO_DC = 25        # Data/Command select
GPIO_RST = 24       # Reset
GPIO_BL = 18        # Backlight (active high)
GPIO_BUTTON = 17    # Button (connected to GND, uses internal pull-up)

# SPI Configuration
SPI_BUS = 0         # SPI bus number
SPI_DEVICE = 0      # SPI device number
SPI_SPEED_SAFE = 10000000  # Recommended stable default; adjust within ~8-12MHz if needed
SPI_SPEED_FAST = 40000000  # Optional faster mode for panels/systems that tolerate it
SPI_SPEED = SPI_SPEED_SAFE
SPI_MODE = 0  # ST7789 uses SPI mode 0
SPI_CSHIGH = False  # Keep CS active-low for stable behavior
SPI_INIT_DELAY_SECONDS = 0.05  # Small settle time after SPI setup
SPI_WRITE_CHUNK_SIZE = 4096  # Chunked writes for stable transfers
SPI_MIN_WRITE_CHUNK_SIZE = 256  # Avoid very small transfers on slower systems

# Display Configuration
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 280
DISPLAY_ROTATION = 0xC0  # MADCTL value: 0xC0 for 180° rotation (MY=1, MX=1)
DISPLAY_OFFSET_X = 0  # X offset for display window
DISPLAY_OFFSET_Y = 20  # Y offset for display window
DISPLAY_INIT_MODE = "safe"  # "safe" for Pi OS Lite stability, "fast" for tuned systems
DISPLAY_ENABLE_INVERSION = False  # Set True when colors appear visibly inverted

# ST7789 Commands
ST7789_NOP = 0x00
ST7789_SWRESET = 0x01
ST7789_SLPIN = 0x10
ST7789_SLPOUT = 0x11
ST7789_NORON = 0x13
ST7789_INVOFF = 0x20
ST7789_INVON = 0x21
ST7789_DISPOFF = 0x28
ST7789_DISPON = 0x29
ST7789_CASET = 0x2A
ST7789_RASET = 0x2B
ST7789_RAMWR = 0x2C
ST7789_MADCTL = 0x36
ST7789_COLMOD = 0x3A

# Button Configuration
BUTTON_DEBOUNCE_MS = 50      # Debounce time in milliseconds
BUTTON_LONG_PRESS_MS = 1000  # Long press threshold in milliseconds

# Backlight Configuration
BACKLIGHT_PWM_FREQ = 1000    # PWM frequency in Hz
BACKLIGHT_DEFAULT_DUTY = 80  # Default brightness (0-100%)

# Data Refresh Configuration
REFRESH_INTERVAL_SECONDS = 80  # Auto-refresh interval for bus data
BUS_ID = "STIF:StopPoint:Q:7800:"
