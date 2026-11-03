"""Start a dedicated local Blender MCP authoring session.

Use a fresh GUI process: blender --factory-startup --python bootstrap_mcp.py --
--addon /path/to/pinned/addon.py --port 9876. The bridge requires Blender's GUI
event loop; its window may be hidden. No third-party asset services are enabled.
"""
import argparse
import hashlib
import importlib.util
from pathlib import Path
import sys

import bpy

parser = argparse.ArgumentParser()
parser.add_argument("--addon", required=True, type=Path)
parser.add_argument("--port", default=9876, type=int)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
expected = "8e193a249e2ed1262f3e794ee2254efd8e3d1f0224385245f2b989154c837083"
if hashlib.sha256(args.addon.read_bytes()).hexdigest() != expected:
    raise RuntimeError("The installed Blender MCP addon differs from the reviewed pinned revision")
if bpy.data.filepath or bpy.data.is_dirty:
    raise RuntimeError("Only a fresh factory-startup authoring process is supported")
if not 1024 <= args.port <= 65535:
    raise ValueError("An unprivileged loopback port is required")
spec = importlib.util.spec_from_file_location("afterlight_blender_mcp", args.addon)
addon = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = addon
spec.loader.exec_module(addon)
addon.register()
scene = bpy.context.scene
scene.blendermcp_auto_start_server = False
for field in ("polyhaven", "hyper3d", "sketchfab", "hunyuan3d", "polypizza", "meshy", "tripo"):
    name = "blendermcp_use_" + field
    if hasattr(scene, name):
        setattr(scene, name, False)
server = addon.BlenderMCPServer(host="127.0.0.1", port=args.port)
bpy.types.blendermcp_server = server
server.start()
print("AFTERLIGHT_MCP_READY", bpy.app.version_string, args.port, flush=True)
