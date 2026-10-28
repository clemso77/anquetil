# Anquetil

Shows the next two bus departures at the Anquetil stop (live data from the
[PRIM Île-de-France Mobilités API](https://prim.iledefrance-mobilites.fr)) with a
dancing bus, on a 240x280 ST7789 SPI screen driven by a Raspberry Pi 5.

- Data refreshes automatically every 80 seconds.
- Pressing the button refreshes immediately.
- The dot in the header shows the state: blue = loading, green = OK, red = error.

## Hardware (BCM numbering)

| Function    | GPIO | Notes                               |
|-------------|------|-------------------------------------|
| DC          | 25   | Display data/command                |
| RST         | 24   | Display reset                       |
| BL          | 18   | Backlight (PWM, 80%)                |
| Button      | 17   | Other leg to GND (internal pull-up) |
| MOSI / SCLK / CS | 10 / 11 / 8 | SPI0, `/dev/spidev0.0`   |

Display VCC goes to 3.3V and GND to ground. SPI must be enabled
(`dtparam=spi=on` in `/boot/firmware/config.txt`, then reboot).

## Code

| File          | Role                                                     |
|---------------|----------------------------------------------------------|
| `main.go`     | Settings, app state, main loop (button + redraw), refresh |
| `api.go`      | Fetches departures from the PRIM stop-monitoring API     |
| `render.go`   | Draws the page                                           |
| `hardware.go` | GPIO (through liblgpio), SPI and the ST7789 driver       |

`assets/` (bus GIF and the Aileron font) is embedded in the binary.
All settings are constants at the top of `main.go`.

## Build and run

```bash
./setup.sh                       # installs golang-go, gcc, liblgpio1 and builds
PRIM_API_KEY=your-key ./anquetil
```

Or build by hand with `go build -o anquetil .`.

The user needs access to the GPIO and SPI devices (`sudo usermod -aG gpio,spi $USER`)
or the program must run as root.

## Run at boot (systemd)

`/etc/systemd/system/anquetil.service`:

```ini
[Unit]
Description=Service Anquetil
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/home/clement/anquetil
ExecStart=/home/clement/anquetil/anquetil
Restart=always
Environment=PRIM_API_KEY=your-key
User=root

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now anquetil
journalctl -u anquetil -f      # logs
```
