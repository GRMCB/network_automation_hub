"""
main.py

Orchestrates the pipeline:

  NetBox (pynetbox) --> transformer.py --> Pyangbind validation
        --> serialize (JSON for records, XML for NETCONF)
        --> write Ansible host_vars for the deploy playbook

Two modes:

  CLI:    python main.py --device spine-01
          One-shot: pull a device, translate, validate, write output files.

  serve:  python main.py serve
          Runs a FastAPI app that NetBox can call as a webhook whenever a
          user saves a change to a device/interface/VLAN. Each webhook
          triggers the same one-shot pipeline for the affected device.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from netbox_client import NetBoxClient
from transformer import convert_device_interfaces

import pyangbind.lib.pybindJSON as pbJ

try:
    from pyangbind.lib.serialise import pybindIETFXMLEncoder
    HAVE_XML_ENCODER = True
except ImportError:
    HAVE_XML_ENCODER = False


load_dotenv()

OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "output"))
ANSIBLE_HOST_VARS_DIR = Path(os.environ.get("ANSIBLE_HOST_VARS_DIR", "ansible_host_vars"))


def process_device(device_name: str) -> dict:
    """
    Run the full pipeline for one device:
      1. Pull interfaces + IPs from NetBox (SoT)
      2. Translate + validate via transformer.py / Pyangbind
      3. Serialize to JSON (for records/debugging) and XML (for NETCONF)
      4. Write an Ansible host_vars file with the NETCONF payload

    Returns a dict summary (useful for the webhook response / CLI output).
    """
    nb = NetBoxClient()

    nb_interfaces = nb.get_interfaces(device_name)
    if not nb_interfaces:
        raise ValueError(f"No interfaces found for device '{device_name}' in NetBox")

    ip_lookup = {}
    for iface in nb_interfaces:
        ip_lookup[iface.id] = nb.get_ip_addresses_for_interface(iface.id)

    # --- Translate + validate (Pyangbind raises on invalid data) ---
    try:
        oc_interfaces = convert_device_interfaces(nb_interfaces, ip_lookup)
    except ValueError as e:
        raise ValueError(
            f"Validation failed for '{device_name}': NetBox data violates "
            f"the OpenConfig model: {e}"
        ) from e

    # --- Serialize to JSON (IETF format) ---
    json_payload = pbJ.dumps(oc_interfaces, mode="ietf")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / f"{device_name}.json"
    json_path.write_text(json_payload)

    result = {
        "device": device_name,
        "interfaces_translated": len(nb_interfaces),
        "json_output": str(json_path),
    }

    # --- Serialize to XML (for NETCONF <edit-config>) ---
    if HAVE_XML_ENCODER:
        xml_payload = pybindIETFXMLEncoder.serialise(oc_interfaces)
        xml_path = OUTPUT_DIR / f"{device_name}.xml"
        xml_path.write_text(xml_payload)
        result["xml_output"] = str(xml_path)
    else:
        xml_payload = None
        result["xml_output"] = None
        result["warning"] = (
            "pybindIETFXMLEncoder unavailable - install a pyangbind version "
            "that includes lib.serialise, or post-process the JSON payload "
            "into XML/NETCONF RPC yourself."
        )

    # --- Write Ansible host_vars ---
    ANSIBLE_HOST_VARS_DIR.mkdir(parents=True, exist_ok=True)
    host_vars_path = ANSIBLE_HOST_VARS_DIR / f"{device_name}.yml"
    host_vars = {
        "openconfig_interfaces_json": json.loads(json_payload),
    }
    if xml_payload:
        host_vars["openconfig_interfaces_xml"] = xml_payload

    host_vars_path.write_text(yaml.safe_dump(host_vars, sort_keys=False))
    result["ansible_host_vars"] = str(host_vars_path)

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cli_main():
    parser = argparse.ArgumentParser(description="NetBox -> OpenConfig translator")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Run the FastAPI webhook receiver")

    parser.add_argument("--device", help="Device name to process (one-shot mode)")
    args = parser.parse_args()

    if args.command == "serve":
        import uvicorn
        uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
        return

    if not args.device:
        parser.error("--device is required unless running 'serve'")

    try:
        result = process_device(args.device)
    except ValueError as e:
        print(f"\u2717 {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\u2713 Translated and validated '{args.device}' against OpenConfig")
    for k, v in result.items():
        print(f"  {k}: {v}")


# ---------------------------------------------------------------------------
# FastAPI webhook receiver (only imported/used when running `serve`)
# ---------------------------------------------------------------------------

from fastapi import FastAPI, Request, HTTPException  # noqa: E402

app = FastAPI(title="NetBox -> OpenConfig Translator")


@app.post("/webhook/netbox")
async def netbox_webhook(request: Request):
    """
    NetBox webhook endpoint.

    Configure this in NetBox under Operations -> Webhooks for the
    dcim.device, dcim.interface, and ipam.ipaddress object types, with
    the URL set to http://translator:8080/webhook/netbox

    NetBox sends a JSON body containing the changed object, including a
    "data" key with the device name (for interfaces, the parent device
    name is under data.device.name).
    """
    body = await request.json()
    data = body.get("data", {})

    device_name = None
    if "device" in data and isinstance(data["device"], dict):
        device_name = data["device"].get("name")
    elif body.get("model") == "device":
        device_name = data.get("name")

    if not device_name:
        raise HTTPException(status_code=400, detail="Could not determine device name from webhook payload")

    try:
        result = process_device(device_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return result


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    cli_main()
