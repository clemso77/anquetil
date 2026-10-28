#!/bin/bash
# Installs build dependencies, checks SPI/GPIO and builds the binary.
set -e

sudo apt update
sudo apt install -y golang-go gcc liblgpio1

if ! ls /dev/spidev* > /dev/null 2>&1; then
    echo "SPI is not enabled: add 'dtparam=spi=on' to /boot/firmware/config.txt and reboot."
    exit 1
fi
[ -e /dev/gpiochip0 ] || echo "Warning: /dev/gpiochip0 not found"

go build -o anquetil .
echo "Built ./anquetil. Run it with: PRIM_API_KEY=... ./anquetil"
