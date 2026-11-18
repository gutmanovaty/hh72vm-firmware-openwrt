// SPDX-License-Identifier: GPL-2.0-or-later

// uow is the unifi-openwrt daemon for Alcatel LINKHUB HH72VM.
package main

import (
	"bytes"
	"flag"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/antoniocosta/unifi-openwrt/internal/device"
	"github.com/antoniocosta/unifi-openwrt/internal/inform"
	"github.com/antoniocosta/unifi-openwrt/internal/models"
	"github.com/antoniocosta/unifi-openwrt/internal/openwrt"
)

func main() {
	informURL := flag.String("url", "http://192.168.1.2:8080/inform", "controller inform URL")
	console := flag.String("console", "192.168.1.2", "console host")
	macStr := flag.String("mac", "", "device MAC (default br-lan MAC)")
	apAddr := flag.String("ap", "local", "AP address (local or host:port)")
	hostname := flag.String("hostname", "Alcatel-HH72VM", "hostname reported to controller")
	modelCode := flag.String("model", "U7PG2", "UniFi model to be adopted as")
	stateDir := flag.String("state", "/etc/unifi-openwrt/state", "state directory")
	suggest := flag.Bool("suggest", false, "suggest closest UniFi models and exit")
	listModels := flag.Bool("models", false, "list UniFi AP models and exit")
	flag.Bool("profile-caps", false, "profile caps")
	flag.Bool("apply", false, "apply settings")
	flag.Bool("stop-on-reset", false, "stop on reset")
	flag.Bool("locate-beep", false, "locate beep")
	flag.String("ssh-listen", "", "fake device SSH")
	flag.String("portal-listen", "", "portal listen")
	flag.String("led-idle", "", "led idle")
	flag.String("uplink-port", "eth0", "uplink port")
	flag.Int("inform-every", 0, "inform interval override")
	flag.Int("hw-caps", 0, "hw caps")
	flag.Int("wifi-caps", 0, "wifi caps")
	flag.Duration("health-every", 0, "health check period")
	flag.Parse()

	log.SetFlags(log.Ldate | log.Ltime)

	if *listModels {
		for _, m := range models.All() {
			fmt.Println(m)
		}
		return
	}

	model, ok := models.Lookup(*modelCode)
	if !ok {
		log.Fatalf("unknown UniFi model %q", *modelCode)
	}
	profile := models.Profile(model)

	ap := openwrt.NewClient(openwrt.Target{Addr: *apAddr})
	defer ap.Close()

	snap, err := ap.Collect()
	if err != nil {
		log.Fatalf("reading AP: %v", err)
	}

	if *suggest {
		d := snap.Describe()
		fmt.Printf("this AP: %q, bands %v, %d streams, Wi-Fi %d\nclosest UniFi models:\n", snap.Model, d.Bands, d.NSS, d.Gen)
		for i, m := range models.Suggest(d) {
			if i == 5 {
				break
			}
			fmt.Println("  ", m)
		}
		return
	}

	if *macStr == "" {
		*macStr = snap.MAC
	}
	mac, err := net.ParseMAC(*macStr)
	if err != nil || len(mac) != 6 {
		log.Fatalf("bad MAC %q", *macStr)
	}

	log.Printf("AP: %q %s, %s, ip %s, %d radios", snap.Model, snap.Release, snap.MAC, snap.IP, len(snap.Radios))

	if err := os.MkdirAll(*stateDir, 0o700); err != nil {
		log.Fatal(err)
	}
	statePath := filepath.Join(*stateDir, "state.json")
	st, found, err := device.Load(statePath)
	if err != nil {
		log.Fatal(err)
	}
	if !found {
		st = device.NewState(*informURL)
		st.Version = profile.Version
	}

	x := &device.Session{
		S: st, Boot: time.Now(), StateDir: *stateDir,
		Dev: inform.Device{
			MAC:          mac,
			IP:           snap.IP,
			Netmask:      snap.Netmask,
			Gateway:      snap.Gateway,
			Hostname:     *hostname,
			Model:        profile.Model,
			ModelDisplay: profile.Display,
		},
	}

	if x.S.HashID == "" {
		h, err := device.NewHashID()
		if err == nil {
			x.S.HashID = h
			_ = x.S.Save(statePath)
		}
	}

	x.SSHPort = 22

	prev := snap
	x.Extra = func() map[string]any {
		s, err := ap.Collect()
		if err == nil {
			prev = s
			if s.IP != "" {
				x.Dev.IP = s.IP
				x.Dev.Netmask = s.Netmask
				x.Dev.Gateway = s.Gateway
			}
		}
		cfg, _ := os.ReadFile(filepath.Join(*stateDir, "system_cfg.txt"))
		info := openwrt.InfoFromCfg(string(cfg))
		f := prev.Fields(nil, info, nil)
		return f
	}

	log.Printf("start: mac=%s ip=%s adopted=%v gcm=%v cfgversion=%s version=%s console=%s",
		mac, snap.IP, x.S.Adopted, x.S.GCM, x.S.CfgVersion, x.S.Version, *console)

	client := &http.Client{Timeout: 10 * time.Second}
	interval := 10 * time.Second

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)

	for {
		if stDisk, found, err := device.Load(statePath); err == nil && found {
			if stDisk.Key != x.S.Key || stDisk.Adopted != x.S.Adopted {
				log.Printf("state updated: adopted=%v key=%s", stDisk.Adopted, stDisk.Key)
				x.S = stDisk
			}
		}

		js, err := x.Payload(time.Now())
		if err != nil {
			log.Printf("payload: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		pkt, err := inform.Encode(x.Dev.MAC, x.S.Key, x.Cipher(), js, nil)
		if err != nil {
			log.Printf("encode: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}

		req, err := http.NewRequest(http.MethodPost, x.S.InformURL, bytes.NewReader(pkt))
		if err != nil {
			log.Printf("request: %v", err)
			time.Sleep(5 * time.Second)
			continue
		}
		req.Header.Set("Content-Type", "application/x-binary")

		resp, err := client.Do(req)
		if err != nil {
			log.Printf("POST %s: %v", x.S.InformURL, err)
			time.Sleep(10 * time.Second)
			continue
		}

		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		switch resp.StatusCode {
		case http.StatusOK:
			log.Printf("inform: HTTP 200 OK (%d bytes reply)", len(body))
		case http.StatusNotFound:
			if !x.S.Adopted {
				log.Printf("inform: HTTP 404 (Pending Adoption on UniFi Controller)")
			} else {
				log.Printf("inform: HTTP 404 while adopted")
			}
		default:
			log.Printf("inform: HTTP %d (%d bytes)", resp.StatusCode, len(body))
		}

		if len(body) > 0 {
			_, plain, err := inform.Decode(body, x.S.Key)
			if err != nil && x.S.Key != inform.DefaultKeyHex {
				_, plain, err = inform.Decode(body, inform.DefaultKeyHex)
			}
			if err != nil {
				log.Printf("reply decode error: %v", err)
			} else {
				out, err := x.Handle(plain, time.Now())
				if err != nil {
					log.Printf("handle error: %v", err)
				} else {
					for _, ev := range out.Events {
						log.Printf("event: %s", ev)
					}
					if out.Changed {
						_ = x.S.Save(statePath)
					}
					if out.Interval > 0 {
						interval = max(time.Duration(out.Interval)*time.Second, time.Second)
					}
				}
			}
		}

		select {
		case <-stop:
			log.Printf("stopped by signal")
			return
		case <-time.After(interval):
		}
	}
}
