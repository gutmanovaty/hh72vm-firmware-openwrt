#!/usr/bin/env python3
import subprocess

SCRIPT = """#!/bin/sh
CMD="$1"
shift
STATE_FILE="/etc/unifi-openwrt/state/state.json"

case "$CMD" in
  set-adopt)
    URL="$1"
    KEY="$2"
    logger -t syswrapper "set-adopt called: URL=$URL KEY=$KEY"
    if [ -f "$STATE_FILE" ] && [ -n "$KEY" ]; then
      sed -i -e "s/\\"key\\": *\\"[^\\"]*\\"/\\"key\\": \\"$KEY\\"/" \\
             -e "s/\\"adopted\\": *false/\\"adopted\\": true/" \\
             -e "s|\\"inform_url\\": *\\"[^\\"]*\\"|\\"inform_url\\": \\"$URL\\"|" "$STATE_FILE"
      killall -HUP uow 2>/dev/null || /etc/init.d/unifi-openwrt restart
    fi
    exit 0
    ;;
  set-inform)
    URL="$1"
    logger -t syswrapper "set-inform called: URL=$URL"
    if [ -f "$STATE_FILE" ] && [ -n "$URL" ]; then
      sed -i "s|\\"inform_url\\": *\\"[^\\"]*\\"|\\"inform_url\\": \\"$URL\\"|" "$STATE_FILE"
      killall -HUP uow 2>/dev/null || /etc/init.d/unifi-openwrt restart
    fi
    exit 0
    ;;
  *)
    logger -t syswrapper "syswrapper called with args: $CMD $@"
    exit 0
    ;;
esac
"""

cmd = [
    'ssh',
    '-o', 'KexAlgorithms=curve25519-sha256',
    '-o', 'HostKeyAlgorithms=+ssh-rsa',
    '-o', 'PubkeyAcceptedKeyTypes=+ssh-rsa',
    '-o', 'Ciphers=aes128-ctr',
    '-o', 'StrictHostKeyChecking=no',
    '-o', 'UserKnownHostsFile=NUL',
    'root@192.168.1.199',
    'cat > /usr/bin/syswrapper.sh && chmod 755 /usr/bin/syswrapper.sh && ls -l /usr/bin/syswrapper.sh'
]

res = subprocess.run(cmd, input=SCRIPT.encode('utf-8'), capture_output=True)
print("OUT:", res.stdout.decode())
if res.stderr:
    print("ERR:", res.stderr.decode()[:100])
