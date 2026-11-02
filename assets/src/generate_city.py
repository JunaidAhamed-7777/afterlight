"""City is generated only from canonical city_manifest.json, never eyeballed roads."""
import bpy,json,math,pathlib
from mathutils import Vector
ROOT=pathlib.Path(__file__).resolve().parents[1]
# Reuse authoring helpers without rerunning the hero generation.
source=(ROOT/'src/generate_assets.py').read_text();helpers=source[source.index('M={}'):source.index('# Hero ambulance')]
exec(helpers)
m=json.loads((ROOT/'map/city_manifest.json').read_text())
for col in list(bpy.data.collections):col.hide_render=True
collection('city_static')
mat('road',(.055,.09,.13));mat('sidewalk',(.38,.43,.43));mat('park',(.22,.40,.34));mat('line',(.69,.70,.59));mat('earth',(.10,.17,.20));mat('hospital',(.80,.85,.80))
box('city foundation',(10,7.5,-3),(1050,1035,5),'earth',4)
# Roads and sidewalks share exact authoritative centerline footprint.
for r in m['roads']:
 for i,(a,b) in enumerate(zip(r['centerline'],r['centerline'][1:])):
  dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy);mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
  angle=-math.atan2(dx,dy)
  for suffix,width,z,ma in [('sidewalk',r['width_m']+2*r['sidewalk_width_m'],.03,'sidewalk'),('road',r['width_m'],.12,'road')]:
   o=box(f"{r['id']}__{i}__{suffix}",(*mid,z),(width,length+.1,.12),ma);o.rotation_euler.z=angle;o['road_id']=r['id']
  # Sparse clear road centre dashes, no texture dependency.
  if r['kind'] not in ['driveway']:
   for d in range(12,int(length)-10,18):
    p=(a[0]+dx*d/length,a[1]+dy*d/length,.19);o=box('road_dash',p,(.18,4,.025),'line');o.rotation_euler.z=angle
for p in m['parcels']:
 if p['kind']=='park':box(p['id'],(*p['center'],.025),(*p['size'],.12),'park')
# Buildings share exactly four simple archetypes, per-instance manifest.
instances=[]
for idx,b in enumerate(m['buildings']):
 x,y=b['center'];w,d=b['size'];h=b['height_m']
 if b['kind']=='hospital':
  box(b['id'],(x,y,h/2),(w,d,h),'hospital',1)
  box(b['id']+'_upper',(x,y,h+2),(w*.73,d*.74,4),'porcelain',.8)
  for z in [6,12,18]:
   box('hospital glazing',(x,y-d/2-.05,z),(w*.90,.14,2.4),'glass')
  box('entry awning',(x,y-d/2-4,5),(18,8,1.3),'mint',.35)
  text('hospital identity','H',(x,y,h+4.05),11,'mint')
  text('hospital name','MEDICAL',(x,y-d/2-.16,22),3.3,'navy',(math.pi/2,0,0))
  instances.append({'id':b['id'],'asset':'hospital','position':[x,y,0],'dimensions':[w,d,h],'baked':True})
 else:
  asset=['building_sand','building_slate','building_clay','building_sage'][idx%4]
  original=bpy.data.objects.get(asset)
  ob=bpy.data.objects.new(b['id'],original.data);active.objects.link(ob);ob.location=(x,y,0);ob.scale=(w,d,h);ob['building_id']=b['id'];ob['archetype']=asset
  instances.append({'id':b['id'],'asset':asset,'position':[x,y,0],'scale':[w,d,h]})
# Pickup anchors are optional overview dots, not baked in city road export.
collection('pickup_markers')
for p in m['pickups']:
 o=cyl(p['id'],(p['position'][0],p['position'][1],.30),.85,.20,'mint',8);o['pickup_id']=p['id']
# Essential overview export: geometry-only static grouping by shared material, instancing manifest separately.
city=bpy.data.collections['city_static'];bpy.ops.object.select_all(action='DESELECT')
for o in city.objects:o.select_set(True)
bpy.context.view_layer.objects.active=list(city.objects)[0];bpy.ops.object.join();bpy.context.object.name='city_static_batched';bpy.context.object['semantic_ids']='../map/city_manifest.json'
bpy.ops.export_scene.gltf(filepath=str(ROOT/'exports/city_static.glb'),export_format='GLB',use_selection=True,export_yup=True,export_extras=True)
(ROOT/'exports/city_instances.json').write_text(json.dumps({'coordinate_system':m['coordinate_system'],'building_instances':instances,'pickups':m['pickups'],'hospitals':m['hospitals'],'source_manifest':'../map/city_manifest.json','note':'city_static.glb includes all building meshes for simple viewer; optimized runtime can instead use shared building archetypes and these transforms, excluding baked buildings to avoid duplicates.'},indent=2))
collection('city_preview_stage')
world=bpy.context.scene.world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.20,.27,.35,1);world.node_tree.nodes['Background'].inputs[1].default_value=.6
bpy.ops.object.light_add(type='SUN',location=(0,0,500));sun=adopt(bpy.context.object,'city sunlight',None);sun.data.energy=2.4;sun.data.angle=.15;sun.rotation_euler=(.45,-.55,-.35)
bpy.ops.object.camera_add(location=(1050,-1350,1150));cam=adopt(bpy.context.object,'city overview camera',None);cam.rotation_euler=(Vector((0,0,0))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=1550;cam.data.clip_end=5000
sc=bpy.context.scene;sc.camera=cam;sc.render.engine='BLENDER_WORKBENCH';sc.display.shading.color_type='MATERIAL';sc.display.shading.show_shadows=True;sc.display.shading.show_cavity=True;sc.eevee.taa_render_samples=16;sc.render.resolution_x=1600;sc.render.resolution_y=1200;sc.render.resolution_percentage=100;sc.render.filepath=str(ROOT/'previews/city_overview.png')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'afterlight_city.blend'))
bpy.ops.render.render(write_still=True)
print('City exported and overview rendered from canonical manifest')
