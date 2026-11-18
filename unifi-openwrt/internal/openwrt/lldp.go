// SPDX-License-Identifier: GPL-2.0-or-later

package openwrt

// LLDP neighbours, read from lldpd (an optional package on the AP). lldpd
// itself sends the AP's own LLDP frames, which is how a UniFi switch learns
// the port the AP is on; here its neighbour list becomes the inform's
// lldp_table. Without lldpd the list is empty.

import (
	"encoding/json"
	"sort"
)

// LLDPNeighbor is one device heard on a port.
type LLDPNeighbor struct {
	Port                  string // local interface (lan1, wan, ...)
	ChassisID, ChassisDes string
	PortID, PortDescr     string
}

// parseLLDP reads "lldpctl -f json0" (every element a list, values under
// "value"). The older "-f json" form, where interfaces and chassis are keyed
// by their name and single elements are not lists, is read too.
func parseLLDP(b []byte) []LLDPNeighbor {
	var root map[string]any
	if json.Unmarshal(b, &root) != nil {
		return nil
	}
	var out []LLDPNeighbor
	for _, l := range lldpList(root["lldp"]) {
		lm, _ := l.(map[string]any)
		for _, e := range lldpList(lm["interface"]) {
			for name, ifc := range lldpNamed(e, "chassis", "port", "via") {
				n := LLDPNeighbor{Port: name}
				for _, c := range lldpList(ifc["chassis"]) {
					for _, ch := range lldpNamed(c, "id", "descr") {
						n.ChassisID, n.ChassisDes = lldpStr(ch["id"]), lldpStr(ch["descr"])
					}
				}
				for _, p := range lldpList(ifc["port"]) {
					if pm, ok := p.(map[string]any); ok {
						n.PortID, n.PortDescr = lldpStr(pm["id"]), lldpStr(pm["descr"])
					}
				}
				if n.Port != "" && n.ChassisID != "" {
					out = append(out, n)
				}
			}
		}
	}
	sort.SliceStable(out, func(i, j int) bool { return out[i].Port < out[j].Port })
	return out
}

// lldpList: a list stays, a single element becomes a list of one.
func lldpList(v any) []any {
	switch t := v.(type) {
	case nil:
		return nil
	case []any:
		return t
	}
	return []any{v}
}

// lldpStr: a plain string, or the "value" of an object or of a list's first
// element.
func lldpStr(v any) string {
	switch t := v.(type) {
	case string:
		return t
	case []any:
		if len(t) > 0 {
			return lldpStr(t[0])
		}
	case map[string]any:
		return lldpStr(t["value"])
	}
	return ""
}

// lldpNamed returns the object(s) in v by name. An object that has one of
// the given keys is the thing itself (its name under "name"); otherwise its
// keys are the names.
func lldpNamed(v any, keys ...string) map[string]map[string]any {
	m, ok := v.(map[string]any)
	if !ok {
		return nil
	}
	for _, k := range keys {
		if _, has := m[k]; has {
			return map[string]map[string]any{lldpStr(m["name"]): m}
		}
	}
	out := map[string]map[string]any{}
	for name, e := range m {
		for _, x := range lldpList(e) {
			if xm, ok := x.(map[string]any); ok {
				out[name] = xm
			}
		}
	}
	return out
}
