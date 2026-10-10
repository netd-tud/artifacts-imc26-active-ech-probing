package main

import (
	"crypto/tls"
	"encoding/base64"
	"encoding/json"
	"flag"
	"fmt"
	"net"
	"os"
	"runtime"
	"runtime/pprof"
	"sort"
	"strings"
	"sync"
	"sync/atomic"
	"time"
)

type config struct {
	host, port, sni string
	count, warmup   int64
	parallel        int
	echB64          string
	useECH          bool
	jsonPath        string
	quiet           bool
	cpuProfilePath  string
	cpuProfileHz    int
}

// Measure latency from the client perspective
type hsStats struct {
	Mean float64 `json:"mean"`
	P50  float64 `json:"p50"`
	P90  float64 `json:"p90"`
	P99  float64 `json:"p99"`
	Max  float64 `json:"max"`
}

type summary struct {
	Host        string  `json:"host"`
	Port        string  `json:"port"`
	SNI         string  `json:"sni"`
	ECH         bool    `json:"ech"`
	Parallel    int     `json:"parallel"`
	Warmup      int64   `json:"warmup"`
	Requested   int64   `json:"requested"`
	OK          int64   `json:"ok"`
	Failed      int64   `json:"failed"`
	ECHAccepted int64   `json:"ech_accepted"`
	WallSeconds float64 `json:"wall_seconds"`
	ConnsPerSec float64 `json:"conns_per_sec"`
	HandshakeMs hsStats `json:"handshake_ms"`
}

func main() {
	c := config{}
	flag.StringVar(&c.host, "host", "127.0.0.1", "server host")
	flag.StringVar(&c.port, "port", "54321", "server port")
	flag.StringVar(&c.sni, "sni", "a.example.com", "(inner) SNI / server_name")
	flag.Int64Var(&c.count, "count", 50000, "number of connections")
	flag.IntVar(&c.parallel, "parallel", 1, "concurrent worker goroutines")
	flag.Int64Var(&c.warmup, "warmup", 1000, "unmeasured warmup connections")
	flag.StringVar(&c.echB64, "ech", "", "ECHConfigList (base64); presence enables ECH")
	flag.StringVar(&c.jsonPath, "json", "", "write JSON summary to PATH (default stdout)")
	flag.BoolVar(&c.quiet, "quiet", false, "suppress human-readable summary on stderr")
	flag.StringVar(&c.cpuProfilePath, "cpuprofile", "", "write a Go CPU profile (measured phase only) to PATH")
	flag.IntVar(&c.cpuProfileHz, "cpuprofhz", 0, "CPU profile sampling rate in Hz (0 = Go's default, ~100)")
	flag.Parse()

	if c.parallel < 1 {
		c.parallel = 1
	}
	c.useECH = c.echB64 != ""

	cfg := &tls.Config{
		ServerName:         c.sni,
		InsecureSkipVerify: true,
		MinVersion:         tls.VersionTLS13,
		MaxVersion:         tls.VersionTLS13,
		// No ClientSessionCache -> every connection is a full handshake.
	}
	if c.useECH {
		ecl, err := decodeB64(c.echB64)
		if err != nil {
			fmt.Fprintf(os.Stderr, "could not base64-decode -ech: %v\n", err)
			os.Exit(1)
		}
		cfg.EncryptedClientHelloConfigList = ecl
	}

	addr := net.JoinHostPort(c.host, c.port)

	// Warmup
	for i := int64(0); i < c.warmup; i++ {
		_, _ = doConn(addr, cfg, c.sni, c.useECH)
	}

	// PROFILE START
	if c.cpuProfilePath != "" {
		f, err := os.Create(c.cpuProfilePath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "create %s: %v\n", c.cpuProfilePath, err)
			os.Exit(1)
		}
		defer f.Close()
		if c.cpuProfileHz > 0 {
			runtime.SetCPUProfileRate(c.cpuProfileHz) // must precede StartCPUProfile
		}
		if err := pprof.StartCPUProfile(f); err != nil {
			fmt.Fprintf(os.Stderr, "start cpu profile: %v\n", err)
			os.Exit(1)
		}
	}

	var ok, failed, echAccepted int64
	remaining := c.count
	var nextErr atomic.Pointer[string]

	type result struct {
		lat             []float64
		ok, failed, ech int64
	}
	results := make([]result, c.parallel)

	var wg sync.WaitGroup
	wall0 := time.Now()
	for w := 0; w < c.parallel; w++ {
		wg.Add(1)
		go func(idx int) {
			defer wg.Done()
			r := &results[idx]
			r.lat = make([]float64, 0, 1024)
			for atomic.AddInt64(&remaining, -1) >= 0 {
				lat, err := doConn(addr, cfg, c.sni, c.useECH)
				if err != nil {
					r.failed++
					if nextErr.Load() == nil {
						s := err.Error()
						nextErr.CompareAndSwap(nil, &s)
					}
					continue
				}
				r.ok++
				if lat.echAccepted {
					r.ech++
				}
				r.lat = append(r.lat, lat.ms)
			}
		}(w)
	}
	wg.Wait()
	// PROFILE END
	wallS := time.Since(wall0).Seconds()
	if c.cpuProfilePath != "" {
		pprof.StopCPUProfile()
	}

	// STATISTICS
	var lats []float64
	for i := range results {
		ok += results[i].ok
		failed += results[i].failed
		echAccepted += results[i].ech
		lats = append(lats, results[i].lat...)
	}

	sum := summary{
		Host: c.host, Port: c.port, SNI: c.sni,
		ECH: c.useECH, Parallel: c.parallel, Warmup: c.warmup,
		Requested: c.count, OK: ok, Failed: failed, ECHAccepted: echAccepted,
		WallSeconds: round4(wallS),
		HandshakeMs: percentiles(lats),
	}
	if wallS > 0 {
		sum.ConnsPerSec = round1(float64(ok) / wallS)
	}

	out, _ := json.MarshalIndent(sum, "", "  ")
	if c.jsonPath != "" && c.jsonPath != "-" && c.jsonPath != "/dev/stdout" {
		if err := os.WriteFile(c.jsonPath, append(out, '\n'), 0o644); err != nil {
			fmt.Fprintf(os.Stderr, "write %s: %v\n", c.jsonPath, err)
			fmt.Println(string(out))
		}
	} else {
		fmt.Println(string(out))
	}

	if !c.quiet {
		fmt.Fprintf(os.Stderr,
			"ok=%d failed=%d ech_accepted=%d  wall=%.2fs  %.0f conns/s  hs mean=%.3fms p99=%.3fms\n",
			ok, failed, echAccepted, wallS, sum.ConnsPerSec, sum.HandshakeMs.Mean, sum.HandshakeMs.P99)
		if c.useECH && echAccepted == 0 && ok > 0 {
			fmt.Fprintln(os.Stderr, "WARNING: ECH was requested but never accepted by the server")
		}
		if failed > 0 {
			if p := nextErr.Load(); p != nil {
				fmt.Fprintf(os.Stderr, "first error: %s\n", *p)
			}
		}
	}
	if ok == 0 && failed > 0 {
		os.Exit(1)
	}
}

type connResult struct {
	ms          float64
	echAccepted bool
}

func doConn(addr string, cfg *tls.Config, sni string, useECH bool) (connResult, error) {
	d := net.Dialer{Timeout: 10 * time.Second}
	raw, err := d.Dial("tcp", addr)
	if err != nil {
		return connResult{}, err
	}
	if tc, ok := raw.(*net.TCPConn); ok {
		tc.SetNoDelay(true)
	}
	conn := tls.Client(raw, cfg)
	_ = conn.SetDeadline(time.Now().Add(15 * time.Second))

	t0 := time.Now()
	err = conn.Handshake()
	ms := float64(time.Since(t0).Microseconds()) / 1000.0
	if err != nil {
		raw.Close()
		return connResult{}, err
	}

	res := connResult{ms: ms, echAccepted: useECH && conn.ConnectionState().ECHAccepted}

	// Send minimal request and close connection
	_, _ = conn.Write([]byte("GET / HTTP/1.1\r\nHost: " + sni + "\r\nConnection: close\r\n\r\n"))
	buf := make([]byte, 4096)
	for {
		if _, err := conn.Read(buf); err != nil {
			break
		}
	}
	conn.Close()
	return res, nil
}

func decodeB64(s string) ([]byte, error) {
	s = strings.Map(func(r rune) rune {
		if r == '\n' || r == '\r' || r == ' ' || r == '\t' {
			return -1
		}
		return r
	}, s)
	return base64.StdEncoding.DecodeString(s)
}

func percentiles(v []float64) hsStats {
	if len(v) == 0 {
		return hsStats{}
	}
	sort.Float64s(v)
	var sum float64
	for _, x := range v {
		sum += x
	}
	pick := func(p float64) float64 { return v[int(p*float64(len(v)-1))] }
	return hsStats{
		Mean: round4(sum / float64(len(v))),
		P50:  round4(pick(0.50)),
		P90:  round4(pick(0.90)),
		P99:  round4(pick(0.99)),
		Max:  round4(v[len(v)-1]),
	}
}

func round4(f float64) float64 { return float64(int64(f*1e4+0.5)) / 1e4 }
func round1(f float64) float64 { return float64(int64(f*10+0.5)) / 10 }
