// SPDX-License-Identifier: GPL-2.0-or-later

package openwrt

import (
	"reflect"
	"testing"
	"time"
)

const lldpJSON0 = `{"lldp":[{"interface":[
 {"name":"lan1","via":"LLDP","rid":"1","age":"0 day, 00:01:23",
  "chassis":[{"id":[{"type":"mac","value":"02:00:00:00:00:01"}],"name":[{"value":"switch"}],"descr":[{"value":"A switch"}],
              "capability":[{"type":"Bridge","enabled":true}]}],
  "port":[{"id":[{"type":"local","value":"Port 5"}],"descr":[{"value":"Port 5"}],"ttl":[{"value":"120"}]}]},
 {"name":"br-lan","via":"LLDP","chassis":[{"id":[{"type":"mac","value":"02:00:00:00:00:02"}]}],"port":[{"id":[{"type":"ifname","value":"eth9"}]}]}
]}]}`

// the same neighbour in the older keyed form
const lldpJSON = `{"lldp":{"interface":{"lan1":{"via":"LLDP","rid":"1",
 "chassis":{"switch":{"id":{"type":"mac","value":"02:00:00:00:00:01"},"descr":"A switch"}},
 "port":{"id":{"type":"local","value":"Port 5"},"descr":"Port 5"}}}}}`

func TestParseLLDP(t *testing.T) {
	want := LLDPNeighbor{Port: "lan1", ChassisID: "02:00:00:00:00:01", ChassisDes: "A switch", PortID: "Port 5", PortDescr: "Port 5"}
	if got := parseLLDP([]byte(lldpJSON0)); len(got) != 2 || got[1] != want || got[0].Port != "br-lan" {
		t.Errorf("json0: %+v", got)
	}
	if got := parseLLDP([]byte(lldpJSON)); !reflect.DeepEqual(got, []LLDPNeighbor{want}) {
		t.Errorf("json: %+v", got)
	}
	for _, in := range []string{"", "not json", `{"lldp":[{}]}`, `{"lldp":{"interface":[]}}`} {
		if got := parseLLDP([]byte(in)); len(got) != 0 {
			t.Errorf("%q: %+v", in, got)
		}
	}
}

// A neighbour on a reported port becomes an lldp_table row with that port's
// number; one on the bridge is left out; no lldpd, no lldp_table.
func TestLLDPTable(t *testing.T) {
	out := `=== board
{"hostname":"ap","model":"m","release":{"description":"OpenWrt"}}
=== port lan1
mac=08:55:66:77:00:01
speed=1000
duplex=full
oper=up
brport=0x1
=== lldp
`
	s, err := Parse([]byte(out+lldpJSON0+"\n"), time.Time{})
	if err != nil {
		t.Fatal(err)
	}
	got, _ := s.Fields(nil, CfgInfo{}, nil)["lldp_table"].([]map[string]any)
	want := []map[string]any{{"local_port_idx": 1, "local_port_name": "lan1", "is_wired": true,
		"chassis_id": "02:00:00:00:00:01", "chassis_descr": "A switch", "port_id": "Port 5", "port_descr": "Port 5"}}
	if !reflect.DeepEqual(got, want) {
		t.Errorf("lldp_table = %v", got)
	}
	s, err = Parse([]byte(out), time.Time{})
	if err != nil {
		t.Fatal(err)
	}
	if _, has := s.Fields(nil, CfgInfo{}, nil)["lldp_table"]; has {
		t.Error("lldp_table without lldpd")
	}
}
