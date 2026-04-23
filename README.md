# anquetil

Simple Raspberry Pi bus display app for a 240x280 ST7789 screen (SPI), with:
- animated bus page
- auto refresh from API
- button handling (short press = refresh, long press = screen off)

## Quick install (recommended)

```bash
git clone https://github.com/clemso77/anquetil.git
cd anquetil
./setup.sh
python3 main.py
```

`setup.sh` installs dependencies, configures permissions (`gpio`, `spi`), and checks SPI.

If the script asks for reboot/re-login, do that first, then run `python3 main.py`.

## Hardware wiring (BCM)

| Function | GPIO |
|---|---|
| DC | 25 |
| RST | 24 |
| BL | 18 |
| Button | 17 |
| SPI MOSI | 10 |
| SPI SCLK | 11 |
| SPI CE0 | 8 |

## Manual install (if needed)

```bash
sudo apt update
sudo apt install -y python3-spidev python3-lgpio python3-pil
sudo usermod -a -G gpio,spi "$USER"
```

Enable SPI in `/boot/firmware/config.txt` (or `/boot/config.txt`) with:

```txt
dtparam=spi=on
```

Then reboot.

## Run

```bash
python3 main.py
```

## Configuration

Main settings are in `config.py`:
- GPIO pins
- SPI speed (`SPI_SPEED`)
- display geometry/offsets
- refresh interval (`REFRESH_INTERVAL_SECONDS`)
- API bus stop (`BUS_ID`)

## Troubleshooting

- **Display blank**: check wiring, SPI enabled (`ls /dev/spidev*`), and try lower `SPI_SPEED` (e.g. `10000000`).
- **Permission errors**: verify user is in `gpio` and `spi` groups, then log out/in.
- **Import errors**: reinstall packages:
  `sudo apt install --reinstall python3-spidev python3-lgpio python3-pil`
