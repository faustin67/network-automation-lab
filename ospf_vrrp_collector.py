#!/usr/bin/env python3
# ============================================================
# ospf_vrrp_collector.py
# Collects OSPF and VRRP data from network devices
# Writes metrics to InfluxDB
# Managed by systemd service: ospf-vrrp-collector
# ============================================================

import subprocess
import requests
import time
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================
INFLUXDB_URL    = "http://172.16.100.100:8086"
INFLUXDB_TOKEN  = "WtG2YclFo9PHmCqS892Nvdxl0U5owEBft7vCwQP2rGhNte6eQdOME2Ue54S2yhCn0J6Ph5N6qwo415JwZXAVTQ=="
INFLUXDB_ORG    = "network-lab"
INFLUXDB_BUCKET = "network-metrics"
COLLECT_INTERVAL = 30  # seconds

ROUTERS = {
    "A-RTR1": "172.16.100.11",
    "A-RTR2": "172.16.100.12",
    "A-RTR3": "172.16.100.13",
}

# ============================================================
# HELPERS
# ============================================================
def ssh_run(host_ip, command):
    try:
        result = subprocess.run(
            ['ssh', '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=5',
             f'faustin@{host_ip}', f'sudo {command}'],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout
    except Exception as e:
        print(f"SSH error to {host_ip}: {e}")
        return ""

def write_to_influxdb(lines):
    url = f"{INFLUXDB_URL}/api/v2/write?org={INFLUXDB_ORG}&bucket={INFLUXDB_BUCKET}&precision=s"
    headers = {
        "Authorization": f"Token {INFLUXDB_TOKEN}",
        "Content-Type": "text/plain"
    }
    data = "\n".join(lines)
    try:
        response = requests.post(url, headers=headers, data=data, timeout=5)
        if response.status_code == 204:
            return True
        else:
            print(f"InfluxDB write error: {response.status_code} {response.text}")
            return False
    except Exception as e:
        print(f"InfluxDB connection error: {e}")
        return False

# ============================================================
# COLLECTORS
# ============================================================
def collect_ospf(hostname, host_ip):
    import re
    lines = []
    output = ssh_run(host_ip, "vtysh -c 'show ip ospf neighbor'")
    neighbours = 0
    full_count = 0
    for line in output.splitlines():
        if re.search(r'\d+\.\d+\.\d+\.\d+', line) and 'Neighbor' not in line:
            neighbours += 1
            if 'Full' in line:
                full_count += 1
    expected = {"A-RTR1": 3, "A-RTR2": 3, "A-RTR3": 2}
    exp = expected.get(hostname, 0)
    timestamp = int(time.time())
    lines.append(f"ospf_neighbours,host={hostname} full={full_count},expected={exp} {timestamp}")
    print(f"  {hostname} OSPF: {full_count}/{exp} neighbours Full")
    return lines

def collect_vrrp(hostname, host_ip):
    lines = []
    output = ssh_run(host_ip, "vtysh -c 'show vrrp'")
    timestamp = int(time.time())
    is_master = 1 if 'Master' in output else 0
    is_backup = 1 if 'Backup' in output else 0
    lines.append(f"vrrp_state,host={hostname} is_master={is_master},is_backup={is_backup} {timestamp}")
    state = "Master" if is_master else "Backup" if is_backup else "Unknown"
    print(f"  {hostname} VRRP: {state}")
    return lines

# ============================================================
# MAIN LOOP
# ============================================================
def main():
    print("=" * 50)
    print("OSPF + VRRP Collector Starting")
    print(f"Interval: {COLLECT_INTERVAL}s")
    print(f"InfluxDB: {INFLUXDB_URL}")
    print("=" * 50)

    while True:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Collecting metrics...")
        all_lines = []

        for hostname, host_ip in ROUTERS.items():
            print(f"\n{hostname} ({host_ip}):")
            all_lines += collect_ospf(hostname, host_ip)
            all_lines += collect_vrrp(hostname, host_ip)

        if all_lines:
            success = write_to_influxdb(all_lines)
            print(f"\nInfluxDB write: {'✅ OK' if success else '❌ FAILED'}")

        print(f"\nSleeping {COLLECT_INTERVAL}s...")
        time.sleep(COLLECT_INTERVAL)

if __name__ == "__main__":
    main()
