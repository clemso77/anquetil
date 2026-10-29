// reseau mesure le coût (CPU, octets, durée) d'une requête à l'API PRIM selon la stratégie :
// connexion neuve ou réutilisée, avec ou sans compression gzip.
//
//	PRIM_API_KEY=... go run ./etude/reseau
package main

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"sync/atomic"
	"syscall"
	"time"
)

var rx, tx atomic.Int64

type countConn struct{ net.Conn }

func (c countConn) Read(b []byte) (int, error) {
	n, err := c.Conn.Read(b)
	rx.Add(int64(n))
	return n, err
}
func (c countConn) Write(b []byte) (int, error) {
	n, err := c.Conn.Write(b)
	tx.Add(int64(n))
	return n, err
}

func cpu() time.Duration {
	var r syscall.Rusage
	syscall.Getrusage(syscall.RUSAGE_SELF, &r)
	return time.Duration(r.Utime.Nano() + r.Stime.Nano())
}

func run(name string, keepAlive, gzip bool, n int) {
	tr := &http.Transport{
		DisableKeepAlives:  !keepAlive,
		DisableCompression: !gzip,
		DialContext: func(ctx context.Context, nw, addr string) (net.Conn, error) {
			c, err := (&net.Dialer{}).DialContext(ctx, nw, addr)
			return countConn{c}, err
		},
	}
	cl := &http.Client{Transport: tr, Timeout: 15 * time.Second}
	url := "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring?MonitoringRef=STIF%3AStopPoint%3AQ%3A7800%3A"
	rx.Store(0)
	tx.Store(0)
	c0, t0 := cpu(), time.Now()
	for i := 0; i < n; i++ {
		req, _ := http.NewRequest("GET", url, nil)
		req.Header.Set("apikey", os.Getenv("PRIM_API_KEY"))
		resp, err := cl.Do(req)
		if err != nil {
			fmt.Println(err)
			return
		}
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}
	fmt.Printf("%-28s CPU/req=%6.1f ms  durée/req=%5.0f ms  reçu/req=%6d o  envoyé/req=%5d o\n", name,
		float64(cpu()-c0)/1e6/float64(n), float64(time.Since(t0).Milliseconds())/float64(n), rx.Load()/int64(n), tx.Load()/int64(n))
}

func main() {
	run("échauffement", true, true, 2)
	run("nouvelle conn + gzip (actuel)", false, true, 30)
	run("nouvelle conn, sans gzip", false, false, 30)
	run("conn réutilisée + gzip", true, true, 30)
	run("conn réutilisée, sans gzip", true, false, 30)
}
