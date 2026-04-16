#!/usr/bin/env python3
import openpyxl
import yaml
import os
import sys

EXCEL_PATH = "/home/faustin/ansible-project/network_lab_v2.xlsx"
HOST_VARS_PATH = "/home/faustin/ansible-project/host_vars"
DRY_RUN = "--dry-run" in sys.argv

def load_sheet(wb, sheet_name):
    ws = wb[sheet_name]
    rows = list(ws.iter_rows(min_row=3, values_only=True))
    headers = [str(h).strip() if h else "" for h in rows[0]]
    data = []
    for row in rows[1:]:
        if not any(cell is not None for cell in row):
            continue
        if row[0] and str(row[0]).startswith("⚠"):
            continue
        record = {}
        for i, header in enumerate(headers):
            if header:
                record[header] = row[i]
        data.append(record)
    return data

def cidr_to_prefix(ip, mask):
    if not ip or not mask:
        return None
    ip = str(ip).strip()
    mask = str(mask).strip()
    if ip == "—" or mask == "—":
        return None
    if "/" in ip:
        return ip
    try:
        bits = sum(bin(int(x)).count("1") for x in mask.split("."))
        return f"{ip}/{bits}"
    except (ValueError, AttributeError):
        return None

role_map = {
    "Ansible Controller": "controller",
    "Management Switch": "mgmt_switch",
    "OSPF Router / VRRP Master": "ospf_vrrp_master",
    "OSPF Router / VRRP Backup": "ospf_vrrp_backup",
    "OSPF Router / CE-A (WAN)": "ospf_ce",
    "OSPF Router / CE-A": "ospf_ce",
    "OSPF Router / CE-A": "ospf_ce",
    "CE-B Router": "ospf_ce",
    "L3 Access Switch": "l3_access",
}

print(f"Reading Excel: {EXCEL_PATH}")
wb = openpyxl.load_workbook(EXCEL_PATH)
devices_data = load_sheet(wb, "1_Devices")
interfaces_data = load_sheet(wb, "3_Interfaces")
ospf_data = load_sheet(wb, "5_OSPF")
vrrp_data = load_sheet(wb, "6_VRRP")
print(f"  Devices: {len(devices_data)}")
print(f"  Interfaces: {len(interfaces_data)}")
print(f"  OSPF entries: {len(ospf_data)}")
print(f"  VRRP entries: {len(vrrp_data)}")

for device in devices_data:
    hostname = device.get("Hostname")
    if not hostname:
        continue
    role_raw = device.get("Role", "")
    role = role_map.get(role_raw, "unknown")
    campus = device.get("Campus/Zone", "").lower().replace("/", "_").replace(" ", "_")
    mgmt_iface = device.get("Mgmt Interface", "ens33")
    loopback_ip = device.get("Loopback IP")
    print(f"\nProcessing: {hostname} ({role})")

    interfaces = {}
    for iface in interfaces_data:
        if iface.get("Hostname") != hostname:
            continue
        iface_name = iface.get("Interface")
        if not iface_name:
            continue
        netplan_type = str(iface.get("Netplan Type", "ethernet")).strip()
        ip = iface.get("IP Address")
        mask = iface.get("Subnet Mask")
        purpose = iface.get("Purpose", "")
        bridge_ifaces = iface.get("Connected To", "")
        cfg = {
            "type": netplan_type if netplan_type != "bond-slave" else "ethernet",
            "comment": str(purpose) if purpose else ""
        }
        cidr = cidr_to_prefix(ip, mask)
        if cidr and ip != "—" and ip is not None:
            cfg["addresses"] = [cidr]
        if iface_name == "ens33":
            cfg["routes"] = [{"to": "default", "via": "172.16.100.1"}]
            cfg["nameservers"] = {"addresses": ["172.16.200.10"]}
        if netplan_type == "bridge":
            members = [b.strip() for b in str(bridge_ifaces).split(",") if b.strip() and b.strip() != "—"]
            if members:
                cfg["interfaces"] = members
        if iface_name == "lo":
            cfg["type"] = "loopback"
        interfaces[iface_name] = cfg

    if "lo" not in interfaces and loopback_ip:
        interfaces["lo"] = {
            "type": "loopback",
            "addresses": [str(loopback_ip).strip()],
            "comment": "OSPF Router-ID"
        }

    ospf = None
    ospf_ifaces = {}
    router_id = None
    for entry in ospf_data:
        if entry.get("Hostname") != hostname:
            continue
        if not router_id:
            router_id = entry.get("Router ID")
        iface_name = entry.get("Interface")
        network = entry.get("Network Statement")
        cost = entry.get("Cost", 10)
        passive = str(entry.get("Passive", "No")).strip().lower() == "yes"
        network_type = entry.get("Network Type")
        if iface_name:
            iface_cfg = {
                "network": str(network).strip() if network else "",
                "cost": int(cost) if cost else 10,
                "passive": passive,
            }
            if network_type and str(network_type).strip() not in ["", "loopback"]:
                iface_cfg["network_type"] = str(network_type).strip()
            ospf_ifaces[str(iface_name).strip()] = iface_cfg
    if router_id and ospf_ifaces:
        ospf = {"router_id": str(router_id).strip(), "area": "0.0.0.0", "interfaces": ospf_ifaces}

    vrrp = []
    for entry in vrrp_data:
        if entry.get("Hostname") != hostname:
            continue
        group = entry.get("VRRP Group")
        interface = entry.get("Interface")
        virtual_ip = entry.get("Virtual IP")
        real_ip = entry.get("Real IP")
        priority = entry.get("Priority", 100)
        preempt = str(entry.get("Preempt", "Yes")).strip().lower() == "yes"
        advert = entry.get("Advert Interval", 1)
        role_vrrp = str(entry.get("Role", "backup")).strip().lower()
        vlan = entry.get("VLAN")
        if group and interface and virtual_ip:
            vrrp.append({
                "group": int(group),
                "interface": str(interface).strip(),
                "virtual_ip": str(virtual_ip).strip(),
                "real_ip": str(real_ip).strip() if real_ip else "",
                "priority": int(priority),
                "preempt": preempt,
                "advert_interval": int(advert),
                "role": role_vrrp,
                "vlan": int(vlan) if vlan else None
            })

    vars_data = {"hostname": hostname, "device_role": role, "campus": campus, "mgmt_interface": "ens33"}
    if interfaces:
        vars_data["interfaces"] = interfaces
    if ospf:
        vars_data["ospf"] = ospf
    if vrrp:
        vars_data["vrrp"] = vrrp

    output_dir = os.path.join(HOST_VARS_PATH, hostname)
    output_file = os.path.join(output_dir, "vars.yaml")

    if DRY_RUN:
        print(f"  [DRY RUN] Would write: {output_file}")
        print(yaml.dump(vars_data, default_flow_style=False, indent=2))
    else:
        os.makedirs(output_dir, exist_ok=True)
        with open(output_file, "w") as f:
            f.write(f"---\n# {hostname} — generated by excel_to_vars.py\n\n")
            yaml.dump(vars_data, f, default_flow_style=False, indent=2, allow_unicode=True)
        print(f"  Written: {output_file}")

print("\nDone!")
