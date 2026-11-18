// SPDX-License-Identifier: GPL-2.0-or-later

package inform

import (
	"encoding/json"
	"errors"
	"net"
	"testing"
)

func testDevice() Device {
	return Device{
		MAC:       testMAC,
		IP:        "192.168.1.50",
		Netmask:   "255.255.255.0",
		Gateway:   "192.168.1.1",
		Hostname:  "unifi-openwrt-test",
		InformURL: "http://192.168.1.1:8080/inform",
		Uptime:    42,
		Time:      1794500000,
	}
}

// TestU7PG2PendingInformOffline is the M0 "done when": build a U7PG2
// pending inform, encode it with the default key, decode it, check fields.
func TestU7PG2PendingInformOffline(t *testing.T) {
	js, err := PendingInform(testDevice())
	if err != nil {
		t.Fatal(err)
	}
	pkt, err := Encode(testMAC, DefaultKeyHex, CBC, js, nil)
	if err != nil {
		t.Fatal(err)
	}
	h, out, err := Decode(pkt, DefaultKeyHex)
	if err != nil {
		t.Fatal(err)
	}
	if h.Flags != 0x0003 {
		t.Errorf("pending inform flags %#04x, want 0x0003 (as the real U7PG2)", h.Flags)
	}
	var m map[string]any
	if err := json.Unmarshal(out, &m); err != nil {
		t.Fatal(err)
	}
	if m["mac"] != h.MAC.String() {
		t.Errorf("payload mac %v != header mac %s", m["mac"], h.MAC)
	}
	for _, k := range requiredPendingFields {
		if _, ok := m[k]; !ok {
			t.Errorf("missing field %q", k)
		}
	}
	want := map[string]any{"model": "U7PG2", "type": "uap", "version": "6.8.2.15592",
		"state": 1.0, "default": true, "fw_caps": 3.0, "inform_url": "http://192.168.1.1:8080/inform"}
	for k, v := range want {
		if m[k] != v {
			t.Errorf("%s = %v, want %v", k, m[k], v)
		}
	}
	// udapi_caps without udapi_version makes the controller drop all caps.
	if _, caps := m["udapi_caps"]; caps {
		if _, ver := m["udapi_version"]; !ver {
			t.Error("udapi_caps without udapi_version")
		}
	}
	radios, _ := m["radio_table"].([]any)
	if len(radios) != 2 {
		t.Fatalf("radio_table has %d radios, want 2", len(radios))
	}
	t.Logf("pending inform: %d bytes JSON, %d bytes on the wire", len(js), len(pkt))
}

// The controller rejects an inform whose inform_ip is not an address, so
// a name in the inform URL ("Override inform host") is looked up.
func TestU7PG2HostnameInformURL(t *testing.T) {
	old := lookupIP
	defer func() { lookupIP = old }()
	calls := 0
	lookupIP = func(h string) ([]net.IP, error) {
		calls++
		if h == "unifi.test" {
			return []net.IP{net.ParseIP("fd00::1"), net.ParseIP("192.0.2.7")}, nil
		}
		return nil, errors.New("no such host")
	}
	d := testDevice()
	d.InformURL = "http://unifi.test:8080/inform"
	for i := 0; i < 2; i++ {
		m, err := U7PG2Fields(d)
		if err != nil {
			t.Fatal(err)
		}
		if m["inform_ip"] != "192.0.2.7" || m["inform_url"] != d.InformURL {
			t.Errorf("inform_ip %v, inform_url %v", m["inform_ip"], m["inform_url"])
		}
	}
	if calls != 1 {
		t.Errorf("%d lookups, want 1 (cached)", calls)
	}
	for _, u := range []string{"http://nowhere.test:8080/inform", "http://[fd00::1]:8080/inform", "http://"} {
		d.InformURL = u
		if _, err := PendingInform(d); err == nil {
			t.Errorf("%s accepted", u)
		}
	}
}

// requiredPendingFields: docs/internals.md (every inform, pending or adopted).
var requiredPendingFields = []string{
	"mac", "serial", "model", "model_display", "type", "version", "ip", "hostname",
	"inform_url", "uptime", "time", "cfgversion", "x_authkey", "default",
	"_default_key", "state", "fw_caps", "isolated", "locating", "selfrun_beacon",
	"radio_table",
}
