package main

import (
	"bytes"
	_ "embed"
	"image"
	"image/color"
	"image/draw"
	"image/gif"
	"math"
	"strconv"
	"strings"
	"time"

	"github.com/fogleman/gg"
	xdraw "golang.org/x/image/draw"
	"golang.org/x/image/font"
	"golang.org/x/image/font/opentype"
)

var (
	//go:embed assets/bus.gif
	busGIF []byte
	//go:embed assets/aileron.ttf
	aileronTTF []byte // the font Pillow's ImageFont.load_default() uses
)

// Layout (pixels).
const (
	title               = "Prochains bus"
	headerY, headerH    = 10, 50
	busWidth            = width * 58 / 100
	busFPS              = 44 // GIF frames per second
	busCenterY          = 83 // middle of the area under the header, nudged up
	cardLeft, cardRight = 12, width - 12
	cardH, cardRadius   = 66, 16
	cardPadX            = 18
)

var cardTops = [2]int{126, 202}

var (
	white      = color.RGBA{255, 255, 255, 255}
	green      = color.RGBA{80, 220, 140, 255}
	red        = color.RGBA{255, 100, 100, 255}
	blue       = color.RGBA{100, 150, 255, 255}
	grey       = color.RGBA{120, 120, 130, 255}
	cardColor  = color.RGBA{46, 42, 34, 255}
	cardBars   = [2]color.RGBA{{255, 200, 60, 255}, {74, 202, 212, 255}}
	stateColor = map[State]color.RGBA{Idle: {180, 180, 190, 255}, Loading: blue, Success: green, Failed: red}
)

type Page struct {
	frames                      []image.Image
	titleFont, huge, big, small font.Face
	start                       time.Time
}

func NewPage() (*Page, error) {
	frames, err := loadFrames(busGIF, busWidth)
	if err != nil {
		return nil, err
	}
	f, err := opentype.Parse(aileronTTF)
	if err != nil {
		return nil, err
	}
	face := func(size float64) font.Face {
		fc, _ := opentype.NewFace(f, &opentype.FaceOptions{Size: size, DPI: 72, Hinting: font.HintingFull})
		return fc
	}
	return &Page{frames: frames, titleFont: face(18), huge: face(50), big: face(30), small: face(16), start: time.Now()}, nil
}

// loadFrames decodes an animated GIF into full frames scaled to the given width.
func loadFrames(data []byte, w int) ([]image.Image, error) {
	g, err := gif.DecodeAll(bytes.NewReader(data))
	if err != nil {
		return nil, err
	}
	canvas := image.NewRGBA(image.Rect(0, 0, g.Config.Width, g.Config.Height))
	size := image.Rect(0, 0, w, g.Config.Height*w/g.Config.Width)
	var frames []image.Image
	for i, fr := range g.Image {
		previous := image.NewRGBA(canvas.Rect)
		copy(previous.Pix, canvas.Pix)

		draw.Draw(canvas, fr.Bounds(), fr, fr.Bounds().Min, draw.Over)
		scaled := image.NewRGBA(size)
		xdraw.CatmullRom.Scale(scaled, size, canvas, canvas.Rect, draw.Src, nil)
		frames = append(frames, scaled)

		switch g.Disposal[i] {
		case gif.DisposalBackground:
			draw.Draw(canvas, fr.Bounds(), image.Transparent, image.Point{}, draw.Src)
		case gif.DisposalPrevious:
			canvas = previous
		}
	}
	return frames, nil
}

// Render draws the whole screen for the given state.
func (p *Page) Render(state State, deps []Departure) *image.RGBA {
	t := time.Since(p.start).Seconds()
	dc := gg.NewContext(width, height)
	dc.SetColor(white)
	dc.Clear()

	// Header: centered title, state dot, spinner while loading.
	tw, th := textSize(p.titleFont, title)
	drawText(dc, p.titleFont, title, (width-tw)/2, headerY+(headerH-th)/2, color.RGBA{25, 25, 35, 255})
	dotX, dotY := float64(width-25)+0.5, float64(headerY+headerH/2)+0.5
	dc.DrawCircle(dotX, dotY, 5.5)
	dc.SetColor(stateColor[state])
	dc.Fill()
	if state == Loading {
		a := gg.Radians(math.Mod(t*360, 360))
		dc.DrawArc(dotX-20, dotY, 4.5, a, a+gg.Radians(270))
		dc.SetLineWidth(3)
		dc.SetColor(blue)
		dc.Stroke()
	}

	// Dancing bus.
	frame := p.frames[int(t*busFPS)%len(p.frames)]
	bounce := float64(int(7 * math.Sin(t*4.2)))
	sway := float64(int(5 * math.Sin(t*2.1)))
	tilt := 5 * math.Sin(t*3.6+0.5)
	cx, cy := width/2+sway, busCenterY+bounce
	dc.Push()
	dc.RotateAbout(gg.Radians(-tilt), cx, cy)
	dc.DrawImageAnchored(frame, int(cx), int(cy), 0.5, 0.5)
	dc.Pop()

	// Two departure cards.
	for i, y := range cardTops {
		bg, bar := cardColor, cardBars[i]
		if state == Failed {
			bg, bar = color.RGBA{60, 40, 40, 255}, red
		}
		fillRoundRect(dc, cardLeft, y, cardRight, y+cardH, bg)
		fillRoundRect(dc, cardLeft, y, cardLeft+10, y+cardH, bar)

		switch {
		case state == Failed:
			if i == 0 {
				drawText(dc, p.small, "ERROR", cardLeft+18, y+22, color.RGBA{255, 150, 150, 255})
			}
		case state == Loading && len(deps) == 0:
			if i == 0 {
				drawText(dc, p.small, "Loading...", cardLeft+18, y+22, white)
			}
		case len(deps) == 0:
			if i == 0 {
				drawText(dc, p.small, "No data", cardLeft+18, y+22, color.RGBA{160, 160, 170, 255})
			}
		case i < len(deps):
			p.drawDeparture(dc, deps[i], y)
		default:
			drawText(dc, p.big, "--", cardLeft+cardPadX, y+18, grey)
			drawText(dc, p.small, "min", cardLeft+cardPadX+40, y+22, grey)
		}
	}
	return dc.Image().(*image.RGBA)
}

// drawDeparture writes "<N> min" on the left of a card and the status on the right.
func (p *Page) drawDeparture(dc *gg.Context, d Departure, top int) {
	cy := top + cardH/2
	wait := strconv.Itoa(waitMinutes(d.Time))
	ww, wh := textSize(p.huge, wait)
	_, mh := textSize(p.big, "min")
	x := cardLeft + cardPadX
	drawText(dc, p.huge, wait, x, cy-wh/2-2, white)
	drawText(dc, p.big, "min", x+ww+6, cy-mh/2+4, white)

	if label, c := statusLabel(d.Status); label != "" {
		sw, sh := textSize(p.small, label)
		drawText(dc, p.small, label, cardRight-14-sw, cy-sh/2, c)
	}
}

// waitMinutes rounds the time left up to the next minute (never negative).
func waitMinutes(departure time.Time) int {
	return max(0, int(math.Floor((time.Until(departure).Seconds()+59)/60)))
}

func statusLabel(status string) (string, color.Color) {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "":
		return "", nil
	case "ontime":
		return "A l'heure", green
	case "delayed":
		return "En retard", red
	case "no_report", "noreport":
		return "Aucun signal", red
	default:
		return "En attente", white
	}
}

// textSize returns the advance width and the ink height of s.
func textSize(f font.Face, s string) (int, int) {
	b, adv := font.BoundString(f, s)
	return adv.Round(), b.Max.Y.Ceil() - b.Min.Y.Floor()
}

// drawText draws s with (x, y) at the top-left of the line, like Pillow's ImageDraw.text.
func drawText(dc *gg.Context, f font.Face, s string, x, y int, c color.Color) {
	dc.SetFontFace(f)
	dc.SetColor(c)
	dc.DrawString(s, float64(x), float64(y+f.Metrics().Ascent.Round()))
}

// fillRoundRect fills the rectangle with inclusive corners (x0,y0)-(x1,y1), like Pillow.
func fillRoundRect(dc *gg.Context, x0, y0, x1, y1 int, c color.Color) {
	w, h := float64(x1-x0+1), float64(y1-y0+1)
	dc.DrawRoundedRectangle(float64(x0), float64(y0), w, h, min(cardRadius, w/2, h/2))
	dc.SetColor(c)
	dc.Fill()
}
