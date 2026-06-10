#!/usr/bin/env bash
#
# build_bindings.sh
#
# ONE-TIME (or CI/CD) build step. Clones the official OpenConfig YANG models
# and compiles the modules needed for this lab into Python classes via
# pyangbind, written to ./oc_bindings/.
#
# This mirrors "Phase 1: Build Time" from the design discussion - re-run this
# whenever:
#   - OpenConfig releases an update you want to pick up
#   - you expand scope to new models (e.g. add openconfig-network-instance
#     for BGP)
#   - a vendor requires a custom YANG extension
#
# Usage:
#   ./build_bindings.sh
#
# Output:
#   ./oc_models/            <- raw cloned YANG source (gitignored)
#   ./oc_bindings/           <- generated Python modules (gitignored)

set -euo pipefail

MODELS_DIR="oc_models"
OUT_DIR="oc_bindings"

mkdir -p "$OUT_DIR"

if [ ! -d "$MODELS_DIR" ]; then
  echo ">> Cloning OpenConfig public YANG models..."
  git clone --depth 1 https://github.com/openconfig/public.git "$MODELS_DIR"
fi

# Locate the pyangbind plugin directory shipped with the pyangbind package
export PYBINDPLUGIN
PYBINDPLUGIN=$(python3 -c "import pyangbind, os; print(os.path.dirname(pyangbind.__file__) + '/plugin')")
echo ">> Using pyangbind plugin dir: $PYBINDPLUGIN"

MODELS_ROOT="$MODELS_DIR/release/models"

# Common include paths - OpenConfig modules cross-reference each other heavily
INCLUDE_PATHS=(
  -p "$MODELS_ROOT"
  -p "$MODELS_ROOT/interfaces"
  -p "$MODELS_ROOT/types"
  -p "$MODELS_ROOT/vlan"
  -p "$MODELS_ROOT/network-instance"
  -p "$MODELS_DIR/third_party/ietf"
)

compile_module () {
  local target_yang="$1"
  local out_file="$2"
  echo ">> Compiling $target_yang -> $OUT_DIR/$out_file"
  pyang --plugindir "$PYBINDPLUGIN" \
        -f pybind \
        "${INCLUDE_PATHS[@]}" \
        -o "$OUT_DIR/$out_file" \
        "$target_yang"
}

# --- Interfaces + IP addressing (Roadmap step 1) ---
compile_module "$MODELS_ROOT/interfaces/openconfig-interfaces.yang" "oc_interfaces.py"

# --- VLANs (Roadmap step 2) ---
compile_module "$MODELS_ROOT/vlan/openconfig-vlan.yang" "oc_vlan.py"

# --- BGP / routing (Roadmap step 3) - uncomment when you get there ---
# compile_module "$MODELS_ROOT/network-instance/openconfig-network-instance.yang" "oc_network_instance.py"
# compile_module "$MODELS_ROOT/bgp/openconfig-bgp.yang" "oc_bgp.py"

touch "$OUT_DIR/__init__.py"

echo ">> Done. Generated modules are in $OUT_DIR/"
echo ">> Import them in transformer.py, e.g.:"
echo "     from oc_bindings.oc_interfaces import openconfig_interfaces"
