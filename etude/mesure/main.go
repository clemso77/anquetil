// mesure échantillonne chaque seconde la puissance du Raspberry Pi 5 (PMIC),
// le CPU d'un processus, le CPU total, le trafic Wi-Fi, la fréquence et la température.
//
//	go run ./etude/mesure -pid 1234 -duree 120 -csv etude/resultats/go.csv -nom "Go"
//	go run ./etude/mesure -pmic   # affiche simplement la lecture brute du PMIC
package main

import (
	"bytes"
	"flag"
	"fmt"
	"log"
	"math"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unsafe"

	"golang.org/x/sys/unix"
)

const userHZ = 100 // ticks/s de /proc/<pid>/stat sous Linux arm64

// pmicRead lance la commande firmware "pmic_read_adc" (comme vcgencmd) via la mailbox /dev/vcio.
func pmicRead() (string, error) {
	f, err := os.OpenFile("/dev/vcio", os.O_RDWR, 0)
	if err != nil {
		return "", err
	}
	defer f.Close()
	const n = 1024
	buf := make([]uint32, 6+n/4+1)
	buf[0] = uint32(len(buf) * 4) // taille totale
	buf[2] = 0x00030080           // tag "get_generic_command"
	buf[3] = n
	copy(unsafe.Slice((*byte)(unsafe.Pointer(&buf[6])), n), "pmic_read_adc")
	if _, _, e := unix.Syscall(unix.SYS_IOCTL, f.Fd(), 0xC0086400, uintptr(unsafe.Pointer(&buf[0]))); e != 0 {
		return "", e
	}
	out := unsafe.Slice((*byte)(unsafe.Pointer(&buf[6])), n)
	return string(out[:bytes.IndexByte(out, 0)]), nil
}

var railRe = regexp.MustCompile(`(\S+)_([AV]) (?:current|volt)\(\d+\)=([\d.]+)`)

// rails suivis individuellement dans le CSV, en plus du total et du cœur CPU.
var rails = []string{"3V7_WL_SW", "DDR_VDD2", "0V8_SW", "1V1_SYS", "1V8_SYS", "3V3_SYS"}

// power renvoie la puissance totale (somme V×I de tous les rails), celle du cœur CPU et celle de chaque rail.
func power() (total, core float64, parRail map[string]float64, err error) {
	s, err := pmicRead()
	if err != nil {
		return 0, 0, nil, err
	}
	amps, volts := map[string]float64{}, map[string]float64{}
	for _, m := range railRe.FindAllStringSubmatch(s, -1) {
		v, _ := strconv.ParseFloat(m[3], 64)
		if m[2] == "A" {
			amps[m[1]] = v
		} else {
			volts[m[1]] = v
		}
	}
	parRail = map[string]float64{}
	for rail, a := range amps {
		parRail[rail] = a * volts[rail]
		total += parRail[rail]
	}
	return total, parRail["VDD_CORE"], parRail, nil
}

func fields(path string) []string {
	b, _ := os.ReadFile(path)
	return strings.Fields(string(b))
}

func atoi(s string) int64 { n, _ := strconv.ParseInt(s, 10, 64); return n }

// procTicks renvoie le temps CPU (utime+stime) d'un processus, en ticks.
func procTicks(pid int) int64 {
	b, _ := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	f := strings.Fields(string(b[bytes.LastIndexByte(b, ')')+1:]))
	if len(f) < 13 {
		return 0
	}
	return atoi(f[11]) + atoi(f[12])
}

// ctxSwitches additionne les changements de contexte de tous les threads d'un processus.
func ctxSwitches(pid int) int64 {
	var n int64
	tasks, _ := filepath.Glob(fmt.Sprintf("/proc/%d/task/*/status", pid))
	for _, t := range tasks {
		b, _ := os.ReadFile(t)
		for _, line := range strings.Split(string(b), "\n") {
			if strings.Contains(line, "ctxt_switches:") {
				n += atoi(strings.Fields(line)[1])
			}
		}
	}
	return n
}

// sysTicks renvoie (total, inactif) depuis /proc/stat.
func sysTicks() (total, idle int64) {
	f := fields("/proc/stat")[1:8]
	for _, x := range f {
		total += atoi(x)
	}
	return total, atoi(f[3]) + atoi(f[4])
}

// wifiBytes renvoie les octets reçus+envoyés par wlan0.
func wifiBytes() int64 {
	b, _ := os.ReadFile("/proc/net/dev")
	for _, line := range strings.Split(string(b), "\n") {
		if l := strings.TrimSpace(line); strings.HasPrefix(l, "wlan0:") {
			f := strings.Fields(strings.TrimPrefix(l, "wlan0:"))
			return atoi(f[0]) + atoi(f[8])
		}
	}
	return 0
}

func readInt(path string) int64 { return atoi(strings.TrimSpace(string(must(os.ReadFile(path))))) }

func must[T any](v T, err error) T {
	if err != nil {
		log.Fatal(err)
	}
	return v
}

type stat struct{ sum, sum2, min, max float64 }

func (s *stat) add(x float64) {
	if s.sum == 0 && s.sum2 == 0 {
		s.min, s.max = x, x
	}
	s.sum += x
	s.sum2 += x * x
	s.min, s.max = math.Min(s.min, x), math.Max(s.max, x)
}

func main() {
	pid := flag.Int("pid", 0, "processus à suivre (0 = aucun)")
	duree := flag.Int("duree", 120, "durée de la mesure en secondes")
	csvPath := flag.String("csv", "", "fichier CSV de sortie (optionnel)")
	nom := flag.String("nom", "mesure", "nom du scénario, pour le résumé")
	brut := flag.Bool("pmic", false, "afficher la lecture brute du PMIC et quitter")
	flag.Parse()

	if *brut {
		fmt.Println(must(pmicRead()))
		return
	}

	var csv *os.File
	if *csvPath != "" {
		csv = must(os.Create(*csvPath))
		defer csv.Close()
		fmt.Fprint(csv, "t,p_total_w,p_core_w,app_cpu_pct,sys_cpu_pct,app_ctx_s,wifi_o_s,freq_mhz,temp_c")
		for _, r := range rails {
			fmt.Fprintf(csv, ",p_%s_w", strings.ToLower(r))
		}
		fmt.Fprintln(csv)
	}

	names := []string{"P totale PMIC (W)", "P cœur CPU (W)", "CPU app (% cœur)", "CPU système (% cœur)",
		"Réveils app (/s)", "Trafic Wi-Fi (o/s)", "Fréquence (MHz)", "Température (°C)"}
	for _, r := range rails {
		names = append(names, "P "+r+" (W)")
	}
	stats := make([]stat, len(names))

	cpu0, ctx0, wifi0 := procTicks(*pid), ctxSwitches(*pid), wifiBytes()
	tot0, idle0 := sysTicks()
	t0 := time.Now()
	for range *duree {
		time.Sleep(time.Second)
		cpu1, ctx1, wifi1 := procTicks(*pid), ctxSwitches(*pid), wifiBytes()
		tot1, idle1 := sysTicks()
		t1 := time.Now()
		dt := t1.Sub(t0).Seconds()
		pTot, pCore, parRail, err := power()
		if err != nil {
			log.Fatalf("lecture PMIC : %v", err)
		}
		row := []float64{
			pTot, pCore,
			100 * float64(cpu1-cpu0) / userHZ / dt,
			400 * (1 - float64(idle1-idle0)/float64(tot1-tot0)), // 4 cœurs, en % d'un cœur
			float64(ctx1-ctx0) / dt,
			float64(wifi1-wifi0) / dt,
			float64(readInt("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")) / 1000,
			float64(readInt("/sys/class/thermal/thermal_zone0/temp")) / 1000,
		}
		for _, r := range rails {
			row = append(row, parRail[r])
		}
		for i, x := range row {
			stats[i].add(x)
		}
		if csv != nil {
			fmt.Fprintf(csv, "%d", t1.Unix())
			for _, x := range row {
				fmt.Fprintf(csv, ",%.3f", x)
			}
			fmt.Fprintln(csv)
		}
		cpu0, ctx0, wifi0, tot0, idle0, t0 = cpu1, ctx1, wifi1, tot1, idle1, t1
	}

	fmt.Printf("Scénario : %s (%d s, pid %d)\n\n", *nom, *duree, *pid)
	fmt.Println("| Indicateur | Moyenne | Écart-type | Min | Max |")
	fmt.Println("|---|---|---|---|---|")
	n := float64(*duree)
	for i, s := range stats {
		mean := s.sum / n
		sd := math.Sqrt(math.Max(0, s.sum2/n-mean*mean))
		fmt.Printf("| %s | %.3f | %.3f | %.3f | %.3f |\n", names[i], mean, sd, s.min, s.max)
	}
}
