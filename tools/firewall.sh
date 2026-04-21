#!/data/data/com.termux/files/usr/bin/sh
# AX12 iptables firewall rules
# Applied on boot via ~/.termux/boot/start-firewall.sh
#
# Policy: drop unsolicited inbound, allow loopback + established,
#         expose SSH (8022) for Tailscale access, block Baidu telemetry.

set -e

IPTABLES="su 0 iptables"

# --- INPUT chain ---
$IPTABLES -F INPUT

# 1. Loopback — unrestricted
$IPTABLES -A INPUT -i lo -j ACCEPT

# 2. Established/related — allows replies to our outbound connections
$IPTABLES -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# 3. SSH on 8022 — Termux sshd (accessible via Tailscale or local WiFi)
$IPTABLES -A INPUT -p tcp --dport 8022 -j ACCEPT

# 4. UMBUS server on 8081 — localhost only
$IPTABLES -A INPUT -p tcp --dport 8081 -s 127.0.0.1 -j ACCEPT

# 5. Drop everything else inbound
$IPTABLES -A INPUT -j DROP

# --- OUTPUT chain (targeted blocks) ---
# Block Baidu location/map telemetry from Flyshark app
$IPTABLES -A OUTPUT -d api.map.baidu.com -j DROP
$IPTABLES -A OUTPUT -d loc.map.baidu.com -j DROP

echo "Firewall rules applied."
$IPTABLES -L INPUT -n --line-numbers
