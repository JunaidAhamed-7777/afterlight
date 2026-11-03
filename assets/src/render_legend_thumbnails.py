"""Render the actual original ambulance/ghost for the desktop legend via MCP.

No source GLB or geometry is changed. Outputs have identical camera/framing,
transparent backgrounds and 320x200 resolution (160x100 CSS pixels at 2x).
"""
import hashlib
import json
from pathlib import Path

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "exports/ambulance.glb"
source_hash = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=str(SOURCE))
models = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
geometry_hashes = {obj.name: hashlib.sha256(b"".join(
    float(value).hex().encode()+b";" for vertex in obj.data.vertices for value in vertex.co)).hexdigest()
    for obj in models}
scene = bpy.context.scene
scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x = 320
scene.render.resolution_y = 200
scene.render.resolution_percentage = 100
scene.render.film_transparent = True
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"
scene.render.image_settings.compression = 90
scene.view_settings.view_transform = "AgX"
scene.view_settings.exposure = -.25
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[0].default_value = (.36,.44,.50,1)
scene.world.node_tree.nodes["Background"].inputs[1].default_value = .45
for name,position,power,size in (("Warm key",(5,4,8),700,6),
                                 ("Soft front",(-4,5,5),500,5),
                                 ("Cool rim",(0,-5,5),450,4)):
    bpy.ops.object.light_add(type="AREA",location=position)
    light = bpy.context.object
    light.name = name
    light.data.energy = power
    light.data.shape = "DISK"
    light.data.size = size
    light.rotation_euler = (Vector((0,0,1.2))-light.location).to_track_quat("-Z","Y").to_euler()
bpy.ops.object.camera_add(location=(8,10,7))
camera = bpy.context.object
camera.rotation_euler = (Vector((0,0,1.25))-camera.location).to_track_quat("-Z","Y").to_euler()
camera.data.type = "ORTHO"
camera.data.ortho_scale = 7.6
camera.data.clip_start = .1
camera.data.clip_end = 100
scene.camera = camera

def render(name):
    path = ROOT / "previews" / name
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    loaded = bpy.data.images.load(str(path), check_existing=False)
    alpha = list(loaded.pixels)[3::4]
    nonempty = sum(value>.001 for value in alpha)
    assert loaded.size[:] == (320,200)
    assert min(alpha) == 0 and nonempty > 1000 and nonempty < len(alpha)*.8
    result = {"file":path.relative_to(ROOT).as_posix(),"bytes":path.stat().st_size,
              "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
              "width":320,"height":200,"alpha_min":min(alpha),
              "alpha_max":max(alpha),"nontransparent_pixels":nonempty}
    bpy.data.images.remove(loaded)
    return result

solid = render("ambulance_model.png")
ghost = bpy.data.materials.new("AFTERLIGHT render-only baseline ghost")
ghost.use_nodes = True
ghost.surface_render_method = "BLENDED"
ghost.use_backface_culling = True
nodes = ghost.node_tree.nodes
nodes.clear()
output = nodes.new("ShaderNodeOutputMaterial")
mix = nodes.new("ShaderNodeMixShader")
transparent = nodes.new("ShaderNodeBsdfTransparent")
emission = nodes.new("ShaderNodeEmission")
rgb = (135/255,215/255,1)
linear = tuple(c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in rgb)
emission.inputs["Color"].default_value = (*linear,1)
emission.inputs["Strength"].default_value = 1
mix.inputs[0].default_value = .38
ghost.node_tree.links.new(transparent.outputs[0],mix.inputs[1])
ghost.node_tree.links.new(emission.outputs[0],mix.inputs[2])
ghost.node_tree.links.new(mix.outputs[0],output.inputs["Surface"])
for obj in models:
    for slot in obj.material_slots:
        slot.link = "OBJECT"
        slot.material = ghost
baseline = render("ghost_model.png")
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == source_hash
for obj in models:
    measured = hashlib.sha256(b"".join(float(value).hex().encode()+b";"
        for vertex in obj.data.vertices for value in vertex.co)).hexdigest()
    assert measured == geometry_hashes[obj.name]
report = {"schema":"afterlight.legend-thumbnails.v1","source":"exports/ambulance.glb",
          "source_sha256":source_hash,"generator":"src/render_legend_thumbnails.py",
          "generator_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          "blender_version":bpy.app.version_string,"bridge":"MCP for Blender 1.8 on loopback",
          "same_camera":True,"geometry_unchanged":True,
          "camera":{"position":list(camera.location),"rotation":list(camera.rotation_euler),
                    "orthographic_scale":camera.data.ortho_scale},
          "ghost":{"color_srgb":"#87D7FF","opacity":.38,"material":"unlit transparent emission; front faces"},
          "images":[solid,baseline],
          "scope":"Actual original model cutouts for the UI legend; Blender rendering is distinct from WebGL screenshots."}
(ROOT/"qa/legend_thumbnails.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
print("LEGEND_THUMBNAILS="+json.dumps(report))
