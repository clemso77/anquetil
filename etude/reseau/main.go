// reseau mesure le coût (CPU, octets, durée) d'une requête à l'API PRIM selon la stratégie :
// connexion neuve ou réutilisée, avec ou sans compression gzip, reprise de session TLS, HTTP/2.
// Il vérifie aussi le support des requêtes conditionnelles (R5) et du filtrage par ligne (R6).
//
//	PRIM_API_KEY=... go run ./etude/reseau
//	PRIM_API_KEY=... go run ./etude/reseau -pause 80s   # la connexion survit-elle au polling ?
package main

import (
	"context"
	"crypto/tls"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptrace"
	"net/url"
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

const base = "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring?MonitoringRef=STIF%3AStopPoint%3AQ%3A7800%3A"

type option struct{ keepAlive, gzip, resume, h2 bool }

func get(cl *http.Client, u string, hdr map[string]string) (*http.Response, []byte, error) {
	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("apikey", os.Getenv("PRIM_API_KEY"))
	for k, v := range hdr {
		req.Header.Set(k, v)
	}
	resp, err := cl.Do(req)
	if err != nil {
		return nil, nil, err
	}
	defer resp.Body.Close()
	b, err := io.ReadAll(resp.Body)
	return resp, b, err
}

func client(o option) *http.Client {
	tr := &http.Transport{
		DisableKeepAlives:  !o.keepAlive,
		DisableCompression: !o.gzip,
		ForceAttemptHTTP2:  o.h2,
		DialContext: func(ctx context.Context, nw, addr string) (net.Conn, error) {
			c, err := (&net.Dialer{}).DialContext(ctx, nw, addr)
			return countConn{c}, err
		},
		TLSClientConfig: &tls.Config{},
	}
	if o.resume {
		tr.TLSClientConfig.ClientSessionCache = tls.NewLRUClientSessionCache(8)
	}
	if !o.h2 {
		tr.TLSNextProto = map[string]func(string, *tls.Conn) http.RoundTripper{} // HTTP/1.1 seulement
	}
	return &http.Client{Transport: tr, Timeout: 15 * time.Second}
}

func run(name string, o option, n int) {
	cl := client(o)
	rx.Store(0)
	tx.Store(0)
	c0, t0 := cpu(), time.Now()
	proto := ""
	for i := 0; i < n; i++ {
		resp, _, err := get(cl, base, nil)
		if err != nil {
			fmt.Println(err)
			return
		}
		proto = resp.Proto
		if resp.TLS != nil && resp.TLS.DidResume {
			proto += " repris"
		}
	}
	fmt.Printf("%-34s CPU/req=%6.1f ms  durée/req=%5.0f ms  reçu/req=%6d o  envoyé/req=%5d o  (%s)\n", name,
		float64(cpu()-c0)/1e6/float64(n), float64(time.Since(t0).Milliseconds())/float64(n), rx.Load()/int64(n), tx.Load()/int64(n), proto)
}

// conditionnel (R5) : le serveur fournit-il ETag / Last-Modified, et répond-il 304 ?
func conditionnel() {
	cl := client(option{keepAlive: true, gzip: true})
	resp, _, err := get(cl, base, nil)
	if err != nil {
		fmt.Println(err)
		return
	}
	etag, lm := resp.Header.Get("ETag"), resp.Header.Get("Last-Modified")
	fmt.Printf("R5 ETag=%q Last-Modified=%q Cache-Control=%q\n", etag, lm, resp.Header.Get("Cache-Control"))
	for k, v := range map[string]string{"If-None-Match": etag, "If-Modified-Since": lm} {
		if v == "" {
			continue
		}
		r, b, err := get(cl, base, map[string]string{k: v})
		if err == nil {
			fmt.Printf("R5 %s -> %s, corps %d o\n", k, r.Status, len(b))
		}
	}
}

// filtrage (R6) : taille de la réponse avec LineRef pour chaque ligne présente à l'arrêt.
func filtrage() {
	cl := client(option{keepAlive: true, gzip: false})
	_, b, err := get(cl, base, nil)
	if err != nil {
		fmt.Println(err)
		return
	}
	var r struct {
		Siri struct {
			ServiceDelivery struct {
				StopMonitoringDelivery []struct {
					MonitoredStopVisit []struct {
						MonitoredVehicleJourney struct{ LineRef struct{ Value string } }
					}
				}
			}
		}
	}
	json.Unmarshal(b, &r)
	lignes := map[string]int{}
	for _, d := range r.Siri.ServiceDelivery.StopMonitoringDelivery {
		for _, v := range d.MonitoredStopVisit {
			lignes[v.MonitoredVehicleJourney.LineRef.Value]++
		}
	}
	fmt.Printf("R6 sans filtre : %d o, passages par ligne %v\n", len(b), lignes)
	for l := range lignes {
		rf, bf, err := get(cl, base+"&LineRef="+url.QueryEscape(l), nil)
		if err == nil {
			fmt.Printf("R6 LineRef=%s -> %s, %d o\n", l, rf.Status, len(bf))
		}
	}
}

// inactivite (R2) : la connexion survit-elle à une pause de la durée du polling ?
func inactivite(pause time.Duration) {
	for _, h2 := range []bool{false, true} {
		cl := client(option{keepAlive: true, gzip: true, h2: h2})
		for i := range 2 {
			if i > 0 {
				time.Sleep(pause)
			}
			reused := false
			ctx := httptrace.WithClientTrace(context.Background(), &httptrace.ClientTrace{
				GotConn: func(c httptrace.GotConnInfo) { reused = c.Reused },
			})
			req, _ := http.NewRequestWithContext(ctx, "GET", base, nil)
			req.Header.Set("apikey", os.Getenv("PRIM_API_KEY"))
			resp, err := cl.Do(req)
			if err != nil {
				fmt.Println(err)
				break
			}
			io.Copy(io.Discard, resp.Body)
			resp.Body.Close()
			if i > 0 {
				fmt.Printf("R2 %s, pause %v : connexion réutilisée = %v\n", resp.Proto, pause, reused)
			}
		}
	}
}

func main() {
	pause := flag.Duration("pause", 0, "si > 0 : teste seulement si la connexion survit à cette pause (ex. 80s)")
	flag.Parse()
	if *pause > 0 {
		inactivite(*pause)
		return
	}
	run("échauffement", option{keepAlive: true, gzip: true}, 2)
	run("nouvelle conn + gzip (actuel)", option{gzip: true}, 30)
	run("nouvelle conn, sans gzip", option{}, 30)
	run("nouvelle conn + gzip + reprise TLS", option{gzip: true, resume: true}, 30)
	run("conn réutilisée + gzip", option{keepAlive: true, gzip: true}, 30)
	run("conn réutilisée, sans gzip", option{keepAlive: true}, 30)
	run("conn réutilisée + gzip, HTTP/2", option{keepAlive: true, gzip: true, h2: true}, 30)
	conditionnel()
	filtrage()
}
