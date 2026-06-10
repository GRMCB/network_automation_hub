"""
transformer.py

The Translation Layer between NetBox (Source of Truth) and OpenConfig
(Pyangbind-validated objects).

Design rules followed here:
  - This module never talks to the NetBox API directly (see netbox_client.py)
    and never serializes/sends payloads (see main.py). It only maps.
  - Every function takes pynetbox object(s) in and returns a Pyangbind
    OpenConfig object out (or raises on invalid data).
  - Pyangbind enforces type/range/regex rules the instant you assign a value.
    A ValueError here means NetBox contains data that does not conform to
    the OpenConfig model - that's the gatekeeper working as intended.

Requires oc_bindings/ to exist - run build_bindings.sh first.
"""

import ipaddress

from oc_bindings.oc_interfaces import openconfig_interfaces
from oc_bindings.oc_vlan import openconfig_vlan


# ---------------------------------------------------------------------------
# Interfaces + IP addressing (Roadmap step 1)
# ---------------------------------------------------------------------------

# NetBox speed is stored in Kbps. Map to OpenConfig SPEED identities.
_SPEED_KBPS_TO_OC = {
    10_000_000: "SPEED_10GB",
    25_000_000: "SPEED_25GB",
    40_000_000: "SPEED_40GB",
    100_000_000: "SPEED_100GB",
    1_000_000: "SPEED_1GB",
}


def convert_netbox_interface_to_openconfig(nb_interface, nb_ip_addresses=None):
    """
    Map a single pynetbox interface (and optionally its IP addresses) into
    an openconfig-interfaces Pyangbind object tree.

    Args:
        nb_interface: a pynetbox Record from dcim.interfaces
        nb_ip_addresses: list of pynetbox Records from ipam.ip_addresses
                         (each .address is CIDR, e.g. "192.168.10.5/24")

    Returns:
        openconfig_interfaces() Pyangbind root object
    """
    oc_root = openconfig_interfaces()

    interface_name = nb_interface.name
    oc_int = oc_root.interfaces.interface.add(interface_name)

    oc_int.config.name = interface_name
    oc_int.config.enabled = bool(nb_interface.enabled)

    if nb_interface.description:
        oc_int.config.description = nb_interface.description

    # Speed: NetBox -> OpenConfig identity enum
    if getattr(nb_interface, "speed", None):
        oc_speed = _SPEED_KBPS_TO_OC.get(nb_interface.speed)
        if oc_speed:
            oc_int.ethernet.config.port_speed = oc_speed
        # If NetBox has a speed we don't have a mapping for yet, we
        # deliberately skip rather than guess - extend _SPEED_KBPS_TO_OC.

    # IP addressing: NetBox stores "192.168.10.5/24" as a single string.
    # OpenConfig requires it nested under subinterfaces/subinterface[0]/ipv4
    # as a separate ip + prefix-length.
    if nb_ip_addresses:
        oc_subint = oc_int.subinterfaces.subinterface.add(0)
        oc_subint.config.index = 0

        for nb_ip in nb_ip_addresses:
            parsed = ipaddress.ip_interface(nb_ip.address)

            if parsed.version != 4:
                # IPv6 handling would go through oc_subint.ipv6 instead -
                # left as a future extension.
                continue

            ip_only = str(parsed.ip)
            prefix_len = parsed.network.prefixlen

            oc_ip = oc_subint.ipv4.addresses.address.add(ip_only)
            oc_ip.config.ip = ip_only
            oc_ip.config.prefix_length = prefix_len

    return oc_root


# ---------------------------------------------------------------------------
# VLANs (Roadmap step 2)
# ---------------------------------------------------------------------------

def convert_netbox_vlan_to_openconfig(nb_vlan):
    """
    Map a pynetbox VLAN object into an openconfig-vlan Pyangbind object tree.

    Args:
        nb_vlan: a pynetbox Record from ipam.vlans

    Returns:
        openconfig_vlan() Pyangbind root object
    """
    oc_vlan_root = openconfig_vlan()

    vlan_entry = oc_vlan_root.vlans.vlan.add(nb_vlan.vid)
    vlan_entry.config.vlan_id = nb_vlan.vid
    vlan_entry.config.name = nb_vlan.name

    # NetBox status is a free-text choice field; OpenConfig wants a fixed enum
    if nb_vlan.status.value == "active":
        vlan_entry.config.status = "ACTIVE"
    else:
        vlan_entry.config.status = "SUSPENDED"

    return oc_vlan_root


# ---------------------------------------------------------------------------
# Convenience: build a full per-device payload from multiple sub-objects
# ---------------------------------------------------------------------------

def convert_device_interfaces(nb_interfaces, ip_lookup):
    """
    Convert all interfaces for a device into a single openconfig-interfaces
    tree (one root object containing every interface).

    Args:
        nb_interfaces: list of pynetbox interface Records for one device
        ip_lookup: dict mapping interface.id -> list of pynetbox IP Records

    Returns:
        openconfig_interfaces() Pyangbind root object containing all interfaces
    """
    oc_root = openconfig_interfaces()

    for nb_interface in nb_interfaces:
        ips = ip_lookup.get(nb_interface.id, [])
        single_iface_tree = convert_netbox_interface_to_openconfig(nb_interface, ips)

        # Merge the single-interface tree's interface entry into oc_root.
        # Pyangbind list containers support direct iteration/copy of entries.
        for name, entry in single_iface_tree.interfaces.interface.items():
            oc_root.interfaces.interface[name] = entry

    return oc_root
