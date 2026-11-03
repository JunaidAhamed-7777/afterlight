"""Inspect actual authored V4 geometry through Blender MCP; no export edits."""
from pathlib import Path
import json

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
graph = json.loads((ROOT / "map/city_manifest.json").read_text())
scene = bpy.context.scene
camera = scene.camera
scene.render.resolution_x = 1600
scene.render.resolution_y = 1000
scene.display.shading.studiolight_rotate_z = .5
scene.display.shading.studiolight_background_alpha = 1
for hospital in graph["hospitals"]:
    b = next(b for b in graph["buildings"] if b["id"] == hospital["building_id"])
    x,y = b["center"]
    camera.location = (x+160,y-220,180)
    target = Vector((x,y,9))
    camera.rotation_euler = (target-camera.location).to_track_quat("-Z","Y").to_euler()
    camera.data.ortho_scale = 225
    scene.render.filepath = str(ROOT / "previews" / (hospital["id"].lower()+"_detail.png"))
    bpy.ops.render.render(write_still=True)
camera.location = (310,-490,200)
camera.rotation_euler = (Vector((175,-300,5))-camera.location).to_track_quat("-Z","Y").to_euler()
camera.data.ortho_scale = 300
scene.render.filepath = str(ROOT / "previews" / "city_street_detail.png")
bpy.ops.render.render(write_still=True)
print("Rendered 2 hospital and 1 neighborhood details from the actual V4 source scene")
