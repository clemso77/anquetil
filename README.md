# Raspberry Pi 5 TFT Display Project

A maintainable Python project for driving a SPI TFT screen (240x280, ST7789-like) on Raspberry Pi 5 running Ubuntu. This project uses only system packages without pip or virtual environments.

## Features

- **ST7789 TFT Display Driver**: Full support for 240x280 pixel displays via SPI
- **Backlight Control**: PWM-based brightness control with on/off toggle
- **Button Input**: Short and long press detection for user interaction
- **Page System**: Easily create and navigate between different display pages
- **Clean Architecture**: Modular code structure for easy maintenance and extension

## Hardware Requirements

- **Raspberry Pi 5** running Ubuntu
- **ST7789 TFT Display** (240x280 pixels, SPI interface)
- **Push Button** (connected to GPIO 17 and GND)

### GPIO Connections (BCM Numbering)

| Function | GPIO Pin | Description |
|----------|----------|-------------|
| DC (Data/Command) | GPIO 25 | Display command/data select |
| RST (Reset) | GPIO 24 | Display reset |
| BL (Backlight) | GPIO 18 | Backlight control (PWM) |
| Button | GPIO 17 | User button (pull-up, connects to GND) |
| SPI MOSI | GPIO 10 | SPI data out (automatic) |
| SPI SCLK | GPIO 11 | SPI clock (automatic) |
| SPI CE0 | GPIO 8 | SPI chip select (automatic) |

### Display Connections

Connect the TFT display to the Raspberry Pi SPI bus:
- **VCC** → 3.3V
- **GND** → Ground
- **MOSI** → GPIO 10 (SPI0 MOSI)
- **SCLK** → GPIO 11 (SPI0 SCLK)
- **CS** → GPIO 8 (SPI0 CE0)
- **DC** → GPIO 25
- **RST** → GPIO 24
- **BL** → GPIO 18

## Software Requirements

### System Packages (Ubuntu)

```bash
sudo apt update
sudo apt install -y python3-spidev python3-lgpio python3-pil
```

These packages provide:
- `python3-spidev`: SPI interface communication
- `python3-lgpio`: GPIO control for Raspberry Pi
- `python3-pil`: Python Imaging Library for graphics

### Enable SPI

SPI must be enabled on your Raspberry Pi:

```bash
# Edit the boot config
sudo nano /boot/firmware/config.txt

# Add or uncomment this line:
dtparam=spi=on

# Save and reboot
sudo reboot
```

Verify SPI is enabled:
```bash
ls /dev/spidev*
# Should show: /dev/spidev0.0 /dev/spidev0.1
```

## Project Structure

```
anquetil/
├── config.py              # Configuration constants (GPIO pins, display settings)
├── main.py                # Main application entry point
├── pages.py               # Page definitions and page manager
├── screen/
│   ├── __init__.py
│   ├── tft.py            # ST7789 TFT display driver
│   └── backlight.py      # Backlight PWM control
└── input/
    ├── __init__.py
    └── button.py          # Button handler with press detection
```

## Installation

1. **Clone the repository:**
   ```bash
   cd ~
   git clone https://github.com/clemso77/anquetil.git
   cd anquetil
   ```

2. **Install system dependencies:**
   ```bash
   sudo apt update
   sudo apt install -y python3-spidev python3-lgpio python3-pil
   ```

3. **Enable SPI** (if not already enabled):
   ```bash
   sudo nano /boot/firmware/config.txt
   # Add: dtparam=spi=on
   sudo reboot
   ```

4. **Run the application:**
   ```bash
   python3 main.py
   ```

## Usage

### Running the Application

```bash
cd ~/anquetil
python3 main.py
```

The application will:
1. Initialize the TFT display
2. Turn on the backlight
3. Display the first page (Welcome page)
4. Wait for button input

### Button Controls

- **Short Press** (< 1 second): Change to the next page
- **Long Press** (≥ 1 second): Toggle backlight on/off
- **Ctrl+C**: Exit the application

### Default Pages

The application includes several demo pages:
1. **Welcome**: Introduction text
2. **Status**: Current time and date
3. **Red**: Solid red screen
4. **Green**: Solid green screen
5. **Blue**: Solid blue screen
6. **Info**: Button usage instructions

## Configuration

Edit `config.py` to customize:

### GPIO Pins
```python
GPIO_DC = 25        # Data/Command
GPIO_RST = 24       # Reset
GPIO_BL = 18        # Backlight
GPIO_BUTTON = 17    # Button
```

### Display Settings
```python
DISPLAY_WIDTH = 240
DISPLAY_HEIGHT = 280
DISPLAY_ROTATION = 0  # 0, 90, 180, or 270 degrees
```

### Button Timing
```python
BUTTON_DEBOUNCE_MS = 50      # Debounce time
BUTTON_LONG_PRESS_MS = 1000  # Long press threshold
```

### Backlight
```python
BACKLIGHT_PWM_FREQ = 1000    # PWM frequency (Hz)
BACKLIGHT_DEFAULT_DUTY = 80  # Default brightness (0-100%)
```

## Extending the Project

### Creating Custom Pages

Create a new page by subclassing the `Page` class:

```python
from pages import Page
from PIL import Image, ImageDraw

class MyCustomPage(Page):
    def __init__(self):
        super().__init__("MyPage")
    
    def render(self):
        # Create your custom image
        image = Image.new('RGB', (240, 280), (100, 100, 100))
        draw = ImageDraw.Draw(image)
        draw.text((50, 100), "Hello!", fill=(255, 255, 255))
        return image
```

Then add it to the page manager in `main.py`:
```python
page_manager.add_page(MyCustomPage())
```

### Modifying Button Behavior

Edit the callback functions in `main.py`:

```python
def _on_short_press(self):
    # Your custom short press action
    pass

def _on_long_press(self):
    # Your custom long press action
    pass
```

## Troubleshooting

### SPI Not Working
- Verify SPI is enabled: `ls /dev/spidev*`
- Check `/boot/firmware/config.txt` has `dtparam=spi=on`
- Reboot after making changes

### Permission Errors
```bash
# Add user to gpio and spi groups
sudo usermod -a -G gpio,spi $USER
# Log out and back in for changes to take effect
```

### Display Not Working
- Check all physical connections
- Verify GPIO pin numbers match your wiring
- Try a slower SPI speed in `config.py`: `SPI_SPEED = 10000000`

### Button Not Responding
- Verify button is connected between GPIO 17 and GND
- Check the button works: `python3 -c "import lgpio; h=lgpio.gpiochip_open(0); lgpio.gpio_claim_input(h, 17, lgpio.SET_PULL_UP); import time; time.sleep(1); print(lgpio.gpio_read(h, 17))"`

### Import Errors
```bash
# Verify packages are installed
dpkg -l | grep python3-spidev
dpkg -l | grep python3-lgpio
dpkg -l | grep python3-pil

# Reinstall if needed
sudo apt install --reinstall python3-spidev python3-lgpio python3-pil
```

## Running at Startup

To run the application automatically at boot:

### Using systemd

1. Create a service file:
   ```bash
   sudo nano /etc/systemd/system/tft-display.service
   ```

2. Add this content:
   ```ini
   [Unit]
   Description=Raspberry Pi TFT Display
   After=multi-user.target

   [Service]
   Type=simple
   User=pi
   WorkingDirectory=/home/pi/anquetil
   ExecStart=/usr/bin/python3 /home/pi/anquetil/main.py
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable tft-display.service
   sudo systemctl start tft-display.service
   ```

4. Check status:
   ```bash
   sudo systemctl status tft-display.service
   ```

## Development

### Code Style

The project follows Python best practices:
- Clear module separation
- Comprehensive docstrings
- Meaningful variable names
- Error handling

### Adding Features

1. Keep modules focused on single responsibilities
2. Update `config.py` for new constants
3. Follow the existing code structure
4. Test on actual hardware

## License

This project is open source. Feel free to modify and distribute.

## Contributing

Contributions are welcome! Please ensure:
- Code follows the existing structure
- Changes are tested on Raspberry Pi hardware
- Documentation is updated

## Credits

Created for Raspberry Pi 5 with Ubuntu, using system packages only for maximum compatibility and maintainability.

## Support

For issues or questions:
1. Check the Troubleshooting section
2. Verify hardware connections
3. Ensure all system packages are installed
4. Check GPIO and SPI permissions