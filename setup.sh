#!/bin/bash
# Setup script for Raspberry Pi TFT Display Project
# This script installs dependencies and configures the system

set -e

echo "===================================="
echo "Raspberry Pi TFT Display Setup"
echo "===================================="
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null && ! grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    echo "Continuing anyway, but hardware features may not work..."
    echo ""
fi

# Update package list
echo "1. Updating package list..."
sudo apt update

# Install required system packages
echo ""
echo "2. Installing system dependencies..."
sudo apt install -y python3-spidev python3-lgpio python3-pil

# Add user to gpio and spi groups for permissions
echo ""
echo "3. Configuring permissions..."
CURRENT_USER=$(whoami)

if ! groups $CURRENT_USER | grep -q "gpio"; then
    echo "   Adding $CURRENT_USER to gpio group..."
    sudo usermod -a -G gpio $CURRENT_USER
    NEED_RELOGIN=1
else
    echo "   User already in gpio group"
fi

if ! groups $CURRENT_USER | grep -q "spi"; then
    echo "   Adding $CURRENT_USER to spi group..."
    sudo usermod -a -G spi $CURRENT_USER
    NEED_RELOGIN=1
else
    echo "   User already in spi group"
fi

# Check if SPI is enabled
echo ""
echo "4. Checking SPI configuration..."
if ! ls /dev/spidev* > /dev/null 2>&1; then
    echo "   SPI is NOT enabled!"
    echo "   To enable SPI:"
    echo "   1. Edit /boot/firmware/config.txt (or /boot/config.txt on older systems)"
    echo "   2. Add or uncomment: dtparam=spi=on"
    echo "   3. Reboot your Raspberry Pi"
    echo ""
    read -p "   Would you like to enable SPI now? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # Try both possible config file locations
        if [ -f /boot/firmware/config.txt ]; then
            CONFIG_FILE="/boot/firmware/config.txt"
        elif [ -f /boot/config.txt ]; then
            CONFIG_FILE="/boot/config.txt"
        else
            echo "   Error: Could not find boot config file"
            exit 1
        fi
        
        echo "   Enabling SPI in $CONFIG_FILE..."
        if grep -q "^dtparam=spi=on" $CONFIG_FILE; then
            echo "   SPI already enabled in config"
        elif grep -q "^#dtparam=spi=on" $CONFIG_FILE; then
            sudo sed -i 's/^#dtparam=spi=on/dtparam=spi=on/' $CONFIG_FILE
            echo "   SPI enabled (uncommented existing line)"
            NEED_REBOOT=1
        else
            echo "dtparam=spi=on" | sudo tee -a $CONFIG_FILE > /dev/null
            echo "   SPI enabled (added new line)"
            NEED_REBOOT=1
        fi
    fi
else
    echo "   SPI is enabled ✓"
fi

# Check GPIO access
echo ""
echo "5. Checking GPIO access..."
if [ -e /dev/gpiochip0 ]; then
    echo "   GPIO chip found ✓"
else
    echo "   Warning: GPIO chip not found at /dev/gpiochip0"
fi

# Summary
echo ""
echo "===================================="
echo "Setup Complete!"
echo "===================================="
echo ""

if [ "${NEED_RELOGIN}" = "1" ]; then
    echo "⚠️  IMPORTANT: Group membership changes require a re-login"
    echo "   Please log out and log back in, then run:"
    echo "   python3 main.py"
    echo ""
fi

if [ "${NEED_REBOOT}" = "1" ]; then
    echo "⚠️  IMPORTANT: SPI configuration requires a reboot"
    echo "   Please reboot your Raspberry Pi:"
    echo "   sudo reboot"
    echo ""
fi

if [ "${NEED_RELOGIN}" != "1" ] && [ "${NEED_REBOOT}" != "1" ]; then
    echo "✓ All checks passed! You can now run the application:"
    echo "  python3 main.py"
    echo ""
fi

echo "For troubleshooting, see the README.md file"
