import bpy,json,pathlib,math
from mathutils import Vector
R=pathlib.Path(__file__).resolve().parents[1]
for name in ['ambulance','car','truck','bike','building_sand','building_slate','building_clay','building_sage']:
 o=bpy.data.objects[name];o['source_front_axis']='+Y';o['front_axis']='-Z';o['up_axis']='+Y';bpy.ops.object.select_all(action='DESELECT');o.select_set(True);bpy.context.view_layer.objects.active=o
 bpy.ops.export_scene.gltf(filepath=str(R/'exports'/f'{name}.glb'),export_format='GLB',use_selection=True,export_yup=True,export_extras=True)
# Ghost is material recipe, not duplicated geometry.
(R/'exports/ghost_material.json').write_text(json.dumps({'mesh':'ambulance.glb','baseColorHex':'#87D7FF','baseColorFactor':[135/255,215/255,1,.28],'emissiveFactor':[.16,.58,.8],'metallicFactor':0,'roughnessFactor':.4,'alphaMode':'BLEND','runtime':{'transparent':True,'depthWrite':False,'depthTest':True,'castShadow':False,'receiveShadow':False,'pickable':False,'bloom':'optional localized; not required','trajectory':'actual synchronized baseline trace, never fabricated lag','queues':'baseline traffic requires separate view; overlay shares only displayed policy traffic'}},indent=2))
sc=bpy.context.scene;sc.render.engine='BLENDER_EEVEE_NEXT';sc.eevee.taa_render_samples=16;cam=sc.camera;sc.render.resolution_x=1000;sc.render.resolution_y=850
for view,pos in [('rear',(-8,-10,6)),('side',(10,0,4))]:
 cam.location=pos;cam.rotation_euler=(Vector((0,0,1.2))-cam.location).to_track_quat('-Z','Y').to_euler();sc.render.filepath=str(R/f'previews/ambulance_{view}.png');bpy.ops.render.render(write_still=True)
# Show ghost alone using shared mesh data; source remains untouched.
hero=bpy.data.objects['ambulance'];ghost=hero.copy();ghost.data=hero.data;ghost.name='baseline_ghost_preview';bpy.data.collections['ambulance'].objects.link(ghost)
for s in ghost.material_slots:s.link='OBJECT';s.material=bpy.data.materials['ghost']
hero.hide_render=True;cam.location=(8,10,7);cam.rotation_euler=(Vector((0,0,1.2))-cam.location).to_track_quat('-Z','Y').to_euler();sc.render.filepath=str(R/'previews/ambulance_ghost.png');bpy.ops.render.render(write_still=True);hero.hide_render=False;ghost.hide_render=True
bpy.ops.wm.save_as_mainfile(filepath=str(R/'afterlight_assets.blend'))
print('Axis metadata fixed; rear/side/ghost previews complete')
