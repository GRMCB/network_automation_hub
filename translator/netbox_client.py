"""
netbox_client.py

Thin wrapper around pynetbox. Keeps API-querying concerns separate from
translation logic (transformer.py) per the "build a mapping translation
layer" guidance: don't mix API query code with data-mapping code.
"""

import os
import pynetbox


class NetBoxClient:
    def __init__(self, url: str | None = None, token: str | None = None):
        self.url = url or os.environ["NETBOX_URL"]
        self.token = token or os.environ["NETBOX_TOKEN"]
        self.api = pynetbox.api(self.url, token=self.token)

    def get_device(self, name: str):
        """Return a pynetbox Device record by name."""
        device = self.api.dcim.devices.get(name=name)
        if device is None:
            raise ValueError(f"Device '{name}' not found in NetBox")
        return device

    def get_interfaces(self, device_name: str):
        """Return all interfaces for a device."""
        return list(self.api.dcim.interfaces.filter(device=device_name))

    def get_ip_addresses_for_interface(self, interface_id: int):
        """Return IP addresses assigned to a given interface."""
        return list(self.api.ipam.ip_addresses.filter(interface_id=interface_id))

    def get_vlans(self, site: str | None = None):
        """Return VLANs, optionally filtered by site."""
        if site:
            return list(self.api.ipam.vlans.filter(site=site))
        return list(self.api.ipam.vlans.all())
