// SPDX-License-Identifier: GPL-2.0-or-later

package device

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// What the controller sends and nothing acts on lands in the ledger, once
// per kind and name, with a count and without secrets.
func TestUnhandledLedger(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "unhandled.json")
	x := &Session{S: NewState("http://192.0.2.1:8080/inform"), StateDir: dir, Unhandled: OpenLedger(path),
		KnownSection: func(s string) bool { return s == "radio" }}
	now := time.Unix(1700000000, 0)
	for i := 0; i < 2; i++ {
		for _, js := range []string{
			`{"_type":"mesh-halt","reason":"x","x_passphrase":"hunter2hunter2"}`,
			`{"_type":"cmd","cmd":"dance","token":"0123456789abcdef0123456789abcdef"}`,
			`{"_type":"noop","interval":5,"server_time_in_utc":"1700000000000","hello":1}`,
			`{"_type":"setparam","mgmt_cfg":"cfgversion=abc\nstun_url=stun://192.0.2.1/\nx_ssh_password=hunter2hunter2\n","system_cfg":"radio.1.channel=6\nteleport.1.x=hunter2hunter2\n"}`,
		} {
			if _, err := x.Handle([]byte(js), now); err != nil {
				t.Fatal(err)
			}
		}
	}
	got := map[string]Unhandled{}
	for _, u := range x.Unhandled.Entries() {
		got[u.Kind+" "+u.Name] = u
	}
	for _, want := range []string{"reply mesh-halt", "cmd dance", "field noop.hello", "field mesh-halt.reason",
		"mgmt_cfg stun_url", "mgmt_cfg x_ssh_password", "system_cfg teleport"} {
		if got[want].Count != 2 {
			t.Errorf("%s: count %d, want 2 (have %v)", want, got[want].Count, got)
		}
	}
	for _, not := range []string{"system_cfg radio", "mgmt_cfg cfgversion", "field setparam.mgmt_cfg"} {
		if _, ok := got[not]; ok {
			t.Errorf("%s is handled and must not be listed", not)
		}
	}
	if s := got["mgmt_cfg stun_url"].Sample; s != "stun://192.0.2.1/" {
		t.Errorf("stun_url sample = %q", s)
	}
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if st, _ := os.Stat(path); st.Mode().Perm() != 0o600 {
		t.Errorf("mode %v, want 600", st.Mode().Perm())
	}
	for _, secret := range []string{"hunter2", "0123456789abcdef"} {
		if strings.Contains(string(b), secret) {
			t.Errorf("the ledger file holds a secret (%s):\n%s", secret, b)
		}
	}
	// a second daemon start reads the file back
	if n := len(OpenLedger(path).Entries()); n != len(got) {
		t.Errorf("reopened ledger has %d entries, want %d", n, len(got))
	}
}

// The ledger stays bounded, and a nil ledger records nothing.
func TestUnhandledLedgerBounds(t *testing.T) {
	l := OpenLedger("")
	now := time.Unix(1700000000, 0)
	for i := 0; i < ledgerMax+20; i++ {
		l.Note("cmd", strings.Repeat("x", i+1), strings.Repeat("s", 1000), now.Add(time.Duration(i)*time.Second))
	}
	e := l.Entries()
	if len(e) != ledgerMax {
		t.Errorf("%d entries, want %d", len(e), ledgerMax)
	}
	if len(e[0].Sample) > ledgerSample+3 {
		t.Errorf("sample of %d bytes", len(e[0].Sample))
	}
	var none *Ledger
	if none.Note("cmd", "x", "", now) || none.Entries() != nil {
		t.Error("a nil ledger must record nothing")
	}
	none.Flush()
}
