// Anquetil: shows the next two bus departures and a dancing bus on an
// ST7789 240x280 SPI screen. Pressing the button refreshes the data.
package main

import (
	"context"
	"log"
	"os"
	"os/signal"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

// Hardware (BCM GPIO numbering).
const (
	pinDC, pinRST, pinBL, pinButton = 25, 24, 18, 17
	spiDevice                       = "/dev/spidev0.0"
	spiSpeed                        = 40_000_000
	width, height                   = 240, 280
	offsetX, offsetY                = 0, 20
	rotation                        = 0xC0 // MADCTL: 180°
	backlightFreq, backlightDuty    = 1000, 80
)

// Behaviour.
const (
	stopPointRef    = "STIF:StopPoint:Q:7800:"
	refreshInterval = 80 * time.Second
	buttonDebounce  = 50 * time.Millisecond
	targetFPS       = 12
)

type State int

const (
	Idle State = iota
	Loading
	Success
	Failed
)

// App holds the data shown on screen. It is shared between the fetch goroutine and the render loop.
type App struct {
	apiKey     string
	refreshing atomic.Bool

	mu         sync.Mutex
	state      State
	departures []Departure
}

// refresh fetches new departures, unless a fetch is already running.
// On error the previous departures are kept.
func (a *App) refresh() {
	if !a.refreshing.CompareAndSwap(false, true) {
		log.Println("Refresh already in progress, skipping")
		return
	}
	defer a.refreshing.Store(false)

	a.mu.Lock()
	a.state = Loading
	a.mu.Unlock()

	deps, err := fetchDepartures(a.apiKey, stopPointRef, 2)

	a.mu.Lock()
	defer a.mu.Unlock()
	if err != nil {
		log.Printf("Error fetching data: %v", err)
		a.state = Failed
		return
	}
	log.Printf("Fetched %d departures: %+v", len(deps), deps)
	a.state, a.departures = Success, deps
}

func (a *App) snapshot() (State, []Departure) {
	a.mu.Lock()
	defer a.mu.Unlock()
	return a.state, a.departures
}

func main() {
	page, err := NewPage()
	if err != nil {
		log.Fatalf("Loading assets: %v", err)
	}
	hw, err := OpenHardware()
	if err != nil {
		log.Fatalf("Initializing hardware: %v", err)
	}
	defer hw.Close()

	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	app := &App{apiKey: os.Getenv("PRIM_API_KEY"), state: Loading}
	go func() {
		for {
			app.refresh()
			select {
			case <-ctx.Done():
				return
			case <-time.After(refreshInterval):
			}
		}
	}()

	log.Printf("Running (auto-refresh every %v, press the button to refresh, Ctrl+C to exit)", refreshInterval)

	// All hardware access happens in this loop: poll the button every 10ms, redraw at targetFPS.
	tick := time.NewTicker(10 * time.Millisecond)
	defer tick.Stop()
	var lastFrame, pressStart time.Time
	for {
		select {
		case <-ctx.Done():
			log.Println("Shutting down")
			return
		case now := <-tick.C:
			if hw.ButtonPressed() {
				if pressStart.IsZero() {
					pressStart = now
				}
			} else if !pressStart.IsZero() {
				if now.Sub(pressStart) >= buttonDebounce {
					log.Println("Button pressed, refreshing")
					go app.refresh()
				}
				pressStart = time.Time{}
			}

			if now.Sub(lastFrame) >= time.Second/targetFPS {
				lastFrame = now
				if err := hw.Show(page.Render(app.snapshot())); err != nil {
					log.Printf("Error updating display: %v", err)
				}
			}
		}
	}
}
