package main

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"time"
)

const apiURL = "https://prim.iledefrance-mobilites.fr/marketplace/stop-monitoring"

var httpClient = &http.Client{Timeout: 15 * time.Second}

type Departure struct {
	Time        time.Time
	Line        string
	Destination string
	Status      string // "onTime", "delayed", "noReport", ...
}

// value is how SIRI wraps most strings: {"value": "..."}.
type value struct {
	Value string `json:"value"`
}

type stopMonitoringResponse struct {
	Siri struct {
		ServiceDelivery struct {
			StopMonitoringDelivery []struct {
				MonitoredStopVisit []struct {
					MonitoringRef           value
					MonitoredVehicleJourney struct {
						LineRef        value
						DestinationRef value
						MonitoredCall  struct {
							ExpectedDepartureTime string
							AimedDepartureTime    string
							DepartureStatus       string
						}
					}
				}
			}
		}
	}
}

// fetchDepartures returns the next `limit` departures from stopRef, soonest first.
func fetchDepartures(apiKey, stopRef string, limit int) ([]Departure, error) {
	if apiKey == "" {
		return nil, errors.New("PRIM_API_KEY environment variable is not set")
	}
	req, err := http.NewRequest("GET", apiURL+"?MonitoringRef="+url.QueryEscape(stopRef), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("apikey", apiKey)
	req.Header.Set("Accept", "application/json")

	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer func() {
		// Drain the body so the connection goes back to the pool (no new TLS handshake next time).
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
	}()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("HTTP %s", resp.Status)
	}

	var body stopMonitoringResponse
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, fmt.Errorf("decoding response: %w", err)
	}

	var deps []Departure
	for _, delivery := range body.Siri.ServiceDelivery.StopMonitoringDelivery {
		for _, visit := range delivery.MonitoredStopVisit {
			journey := visit.MonitoredVehicleJourney
			call := journey.MonitoredCall
			ts := call.ExpectedDepartureTime
			if ts == "" {
				ts = call.AimedDepartureTime
			}
			t, err := time.Parse(time.RFC3339, ts)
			if visit.MonitoringRef.Value != stopRef || err != nil {
				continue
			}
			deps = append(deps, Departure{t, journey.LineRef.Value, journey.DestinationRef.Value, call.DepartureStatus})
		}
	}
	sort.Slice(deps, func(i, j int) bool { return deps[i].Time.Before(deps[j].Time) })
	return deps[:min(limit, len(deps))], nil
}
