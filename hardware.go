package main

// GPIO goes through liblgpio, mainly
// for its accurate software PWM on the backlight pin.

// #cgo LDFLAGS: -l:liblgpio.so.1
// int lgGpiochipOpen(int gpioDev);
// int lgGpiochipClose(int handle);
// int lgGpioClaimInput(int handle, int lFlags, int gpio);
// int lgGpioClaimOutput(int handle, int lFlags, int gpio, int level);
// int lgGpioRead(int handle, int gpio);
// int lgGpioWrite(int handle, int gpio, int level);
// int lgTxPwm(int handle, int gpio, float pwmFrequency, float pwmDutyCycle, int pwmOffset, int pwmCycles);
import "C"

import (
	"errors"
	"fmt"
	"image"
	"os"
	"time"

	"golang.org/x/sys/unix"
)

const lgSetPullUp = 32

// ST7789 commands.
const (
	cmdSWRESET = 0x01
	cmdSLPIN   = 0x10
	cmdSLPOUT  = 0x11
	cmdNORON   = 0x13
	cmdINVON   = 0x21
	cmdDISPOFF = 0x28
	cmdDISPON  = 0x29
	cmdCASET   = 0x2A
	cmdRASET   = 0x2B
	cmdRAMWR   = 0x2C
	cmdMADCTL  = 0x36
	cmdCOLMOD  = 0x3A
)

// spidev ioctls: _IOW('k', 1, u8) and _IOW('k', 4, u32).
const (
	spiIocWrMode       = 0x40016b01
	spiIocWrMaxSpeedHz = 0x40046b04
)

type Hardware struct {
	chip  C.int
	spi   *os.File
	frame []byte // RGB565 buffer reused for every frame
}

func lgCheck(what string, rc C.int) error {
	if rc < 0 {
		return fmt.Errorf("%s: lgpio error %d", what, rc)
	}
	return nil
}

// OpenHardware claims the GPIOs, opens SPI, initializes the screen and turns the backlight on.
func OpenHardware() (*Hardware, error) {
	chip := C.lgGpiochipOpen(0)
	if err := lgCheck("open gpiochip0", chip); err != nil {
		return nil, err
	}
	hw := &Hardware{chip: chip, frame: make([]byte, width*height*2)}

	err := errors.Join(
		lgCheck("claim DC", C.lgGpioClaimOutput(chip, 0, pinDC, 0)),
		lgCheck("claim RST", C.lgGpioClaimOutput(chip, 0, pinRST, 0)),
		lgCheck("claim BL", C.lgGpioClaimOutput(chip, 0, pinBL, 0)),
		lgCheck("claim button", C.lgGpioClaimInput(chip, lgSetPullUp, pinButton)),
	)
	if err == nil {
		hw.spi, err = os.OpenFile(spiDevice, os.O_RDWR, 0)
	}
	if err == nil {
		fd := int(hw.spi.Fd())
		err = errors.Join(
			unix.IoctlSetPointerInt(fd, spiIocWrMode, 0),
			unix.IoctlSetPointerInt(fd, spiIocWrMaxSpeedHz, spiSpeed),
		)
	}
	if err != nil {
		hw.Close()
		return nil, err
	}

	// Hardware reset, then init sequence.
	for _, level := range []C.int{1, 0, 1} {
		C.lgGpioWrite(chip, pinRST, level)
		time.Sleep(10 * time.Millisecond)
	}
	time.Sleep(110 * time.Millisecond)
	hw.command(cmdSWRESET)
	time.Sleep(150 * time.Millisecond)
	hw.command(cmdSLPOUT)
	time.Sleep(50 * time.Millisecond)
	hw.command(cmdCOLMOD, 0x55) // 16 bits per pixel
	hw.command(cmdMADCTL, rotation)
	hw.command(cmdINVON) // this panel needs inverted colors
	time.Sleep(10 * time.Millisecond)
	hw.command(cmdNORON)
	time.Sleep(10 * time.Millisecond)
	hw.command(cmdDISPON)
	time.Sleep(10 * time.Millisecond)

	C.lgTxPwm(chip, pinBL, backlightFreq, backlightDuty, 0, 0)
	return hw, nil
}

// write sends bytes with DC low (command) or high (data), in 4096-byte chunks (spidev's buffer size).
func (hw *Hardware) write(dc C.int, data []byte) error {
	C.lgGpioWrite(hw.chip, pinDC, dc)
	for len(data) > 0 {
		n := min(len(data), 4096)
		if _, err := hw.spi.Write(data[:n]); err != nil {
			return err
		}
		data = data[n:]
	}
	return nil
}

func (hw *Hardware) command(cmd byte, data ...byte) error {
	err := hw.write(0, []byte{cmd})
	if err == nil && len(data) > 0 {
		err = hw.write(1, data)
	}
	return err
}

// Show sends a full-screen image to the display.
func (hw *Hardware) Show(img *image.RGBA) error {
	i := 0
	for y := range height {
		for x := range width {
			p := img.Pix[img.PixOffset(x, y):]
			c := uint16(p[0]&0xF8)<<8 | uint16(p[1]&0xFC)<<3 | uint16(p[2]>>3)
			hw.frame[i], hw.frame[i+1] = byte(c>>8), byte(c)
			i += 2
		}
	}
	x0, x1 := offsetX, offsetX+width-1
	y0, y1 := offsetY, offsetY+height-1
	return errors.Join(
		hw.command(cmdCASET, byte(x0>>8), byte(x0), byte(x1>>8), byte(x1)),
		hw.command(cmdRASET, byte(y0>>8), byte(y0), byte(y1>>8), byte(y1)),
		hw.command(cmdRAMWR),
		hw.write(1, hw.frame),
	)
}

// ButtonPressed reports whether the button is held down (it pulls the pin to GND).
func (hw *Hardware) ButtonPressed() bool {
	return C.lgGpioRead(hw.chip, pinButton) == 0
}

// Close puts the screen to sleep, turns off the backlight and releases everything.
func (hw *Hardware) Close() {
	if hw.spi != nil {
		hw.command(cmdDISPOFF)
		time.Sleep(10 * time.Millisecond)
		hw.command(cmdSLPIN)
		time.Sleep(120 * time.Millisecond) // datasheet: 120ms after SLPIN
		hw.spi.Close()
	}
	C.lgTxPwm(hw.chip, pinBL, 0, 0, 0, 0) // frequency 0 stops the PWM
	C.lgGpioWrite(hw.chip, pinBL, 0)
	C.lgGpiochipClose(hw.chip)
}
