# Network Automation Lab

**Enterprise Network Automation & Monitoring Platform**

A home-based network automation lab simulating a real enterprise campus network with two sites, built to develop and demonstrate enterprise networking, automation, and AI-powered monitoring skills.

---

## Lab Overview

| Parameter | Details |
|---|---|
| Platform | VMware Workstation + GNS3 + Ubuntu 24.04 |
| Routing Engine | FRR (Free Range Routing) |
| Automation | Ansible + Python + Jinja2 |
| Monitoring | Grafana + InfluxDB + Python SSH Collector |
| Source of Truth | Excel Workbook (9 tabs) |
| AI Integration | Claude API (Anthropic) — Phase 5 |

---

## Network Topology

```
Campus A (Active)                    Campus B (Standby)
─────────────────                    ─────────────────
A-RTR1 (VRRP Master)                 B-RTR1 (CE-B)
A-RTR2 (VRRP Backup)    ── WAN ──    B-SW1
A-RTR3 (CE-A)
A-SW1 / A-SW2
CTRL (Ansible Controller)
```

**Campus A uses a triangle OSPF topology** — A-RTR1, A-RTR2, and A-RTR3 form a fully redundant triangle providing ECMP load balancing and sub-40-second reconvergence on any link failure.

---

## Protocols & Technologies Implemented

### Routing — OSPFv2
- Single Area 0 backbone
- Triangle redundancy topology across 3 routers
- ECMP load balancing across equal-cost paths
- Loopback /32 interfaces as stable OSPF Router-IDs
- Sub-40-second convergence on link failure

### Gateway Redundancy — VRRP
- Group 2 on VLAN 200 — VIP 172.16.200.254
- A-RTR1 as Master (priority 110), A-RTR2 as Backup (priority 100)
- Sub-3-second failover demonstrated and tested
- Preemption enabled — Master reclaims role on recovery

### VLANs
| VLAN | Name | Subnet | Purpose |
|---|---|---|---|
| 100 | Management | 172.16.100.0/24 | Device management |
| 101 | Users-A | 172.16.101.0/24 | Campus A end users |
| 102 | Users-B | 172.16.102.0/24 | Campus B end users |
| 200 | Shared-Data | 172.16.200.0/24 | Shared services + VRRP |

---

## Automation Pipeline

```
Excel (Source of Truth)
        ↓
excel_to_vars.py (Python)
        ↓
host_vars YAML files (per device)
        ↓
Jinja2 Templates (.j2)
        ↓
Ansible Playbooks
        ↓
Network Devices
```

**3-step workflow for any network change:**
1. Update `network_lab_v2.xlsx`
2. Run `python3 excel_to_vars.py`
3. Run `ansible-playbook playbooks/deploy_frr.yaml`

### Key Files

| File | Purpose |
|---|---|
| `excel_to_vars.py` | Reads 9-tab Excel workbook, generates per-device Ansible vars |
| `templates/frr.j2` | Jinja2 template — FRR OSPF + VRRP config for all routers |
| `templates/netplan_router.j2` | Jinja2 template — Netplan interface config for routers |
| `templates/netplan_switch.j2` | Jinja2 template — Netplan interface config for switches |
| `playbooks/deploy_frr.yaml` | Ansible — push FRR OSPF + VRRP config to all routers |
| `playbooks/deploy_netplan.yaml` | Ansible — push Netplan interface configs to all devices |
| `playbooks/preflight.yaml` | Ansible — install and verify all daemons on fresh devices |
| `ospf_vrrp_collector.py` | Python SSH collector — collects OSPF/VRRP metrics every 30s |
| `network_lab_v2.xlsx` | 9-tab Excel source of truth — all network parameters |

### Three Deployment Modes

| Mode | Scope | Command |
|---|---|---|
| Per device | Single device only | `--limit A-RTR1` |
| Per campus | All Campus A devices | `--limit campus_a` |
| All devices | Full lab push | No limit flag + confirmation prompt |

---

## Monitoring Stack

```
Network Devices (RTR1, RTR2, RTR3)
        ↓
ospf_vrrp_collector.py (Python SSH — every 30s)
        ↓
InfluxDB 2.7.4 (Time Series Database)
        ↓
Grafana 11.6.0 (Live Dashboard)
```

### What is Monitored
| Measurement | Fields | Description |
|---|---|---|
| ospf_neighbours | full, expected | Actual vs design target neighbour count per router |
| vrrp_state | is_master, is_backup | VRRP role per router |
| ospf_health | healthy | 1 = all neighbours Full, 0 = degraded |

### Collector Service
The collector runs as a **systemd service** — auto-starts on boot, single instance enforced, auto-restarts on crash.

```bash
# Start
sudo systemctl start ospf-vrrp-collector

# Stop
sudo systemctl stop ospf-vrrp-collector

# Status
sudo systemctl status ospf-vrrp-collector

# Live logs
sudo journalctl -u ospf-vrrp-collector -f
```

---

## Failover Testing

### OSPF Link Failure Test
```bash
# Bring down RTR1-RTR3 link
ansible A-RTR1 -m command -a "ip link set ens39 down" -b -i inventory/hosts.yaml

# Watch Grafana dashboard — RTR1 drops 3→2, RTR3 drops 2→1 within 40s

# Restore link
ansible A-RTR1 -m command -a "ip link set ens39 up" -b -i inventory/hosts.yaml
```

### VRRP Failover Test
```bash
# Continuous ping to VIP
ping 172.16.200.254 -c 1000

# Reboot Master router
ansible A-RTR1 -m command -a "reboot" -b -i inventory/hosts.yaml

# Result: RTR2 promotes to Master within 3 seconds
# Max 3 ping packets dropped
```

---

## Device Inventory

| Device | Role | Management IP | Status |
|---|---|---|---|
| CTRL | Ansible Controller | 172.16.100.100 | Active |
| MGMT-SW | Management Switch | 172.16.100.1 | Active |
| A-RTR1 | OSPF Router / VRRP Master | 172.16.100.11 | Active |
| A-RTR2 | OSPF Router / VRRP Backup | 172.16.100.12 | Active |
| A-RTR3 | OSPF Router / CE-A | 172.16.100.13 | Active |
| A-SW1 | L3 Access Switch | 172.16.100.15 | Active |
| A-SW2 | L3 Access Switch | 172.16.100.16 | Active |
| B-RTR1 | CE-B Router | 172.16.100.14 | Standby |
| B-SW1 | L3 Access Switch | 172.16.100.17 | Standby |

---

## Future Phases

| Phase | Topic | Technologies |
|---|---|---|
| Phase 2 | MPLS Core + BGP | FRR MPLS, LDP, MP-BGP, PE/P routers |
| Phase 3 | NETCONF/RESTCONF | YANG models, ncclient, REST API |
| Phase 4 | Spine-Leaf | BGP EVPN, VXLAN |
| Phase 5 | AI Monitoring Agent | Claude API, auto-remediation, predictive analysis |

---

## Tech Stack

![Python](https://img.shields.io/badge/Python-3.12-blue)
![Ansible](https://img.shields.io/badge/Ansible-9.2-red)
![Ubuntu](https://img.shields.io/badge/Ubuntu-24.04-orange)
![Grafana](https://img.shields.io/badge/Grafana-11.6-yellow)
![InfluxDB](https://img.shields.io/badge/InfluxDB-2.7-purple)
![FRR](https://img.shields.io/badge/FRR-8.4-green)

---

*Built by Faustin Anthonipillai — Senior Network Engineer*
