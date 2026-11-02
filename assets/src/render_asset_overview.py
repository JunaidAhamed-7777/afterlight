"""Presentation only. Import frozen GLBs without modifying source assets.
Run via Blender MCP with __file__ set. Panels deliberately not to scale.
"""
import bpy, pathlib,json,math
from mathutils import Matrix,Vector,Euler
R=pathlib.Path(__file__).resolve().parents[1]
scene=bpy.data.scenes.new('Afterlight Asset Overview');bpy.context.window.scene=scene
scene.world=bpy.data.worlds.new('Overview world');scene.world.color=(.10,.14,.19)
def material(n,c):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,1);return m
ink=material('overview ink',(.95,.97,1));muted=material('overview muted',(.65,.75,.84));tilemat=material('overview panel',(.035,.065,.095));cyan=material('overview ghost cyan',(.529,.843,1))
def label(t,x,y,size=.36,mat=ink):
 c=bpy.data.curves.new(t,'FONT');c.body=t;c.size=size;c.resolution_u=2;c.materials.append(mat);o=bpy.data.objects.new(t,c);scene.collection.objects.link(o);o.location=(x,y,30);return o
def tile(x,y,w,h):
 bpy.ops.mesh.primitive_cube_add(size=1,location=(x,y,-15));o=bpy.context.object;o.scale=(w,h,.08);o.data.materials.append(tilemat)
def load(name,position,scale,rot=(.85,0,-.45),ghost=False,crop=None):
 before=set(scene.objects);bpy.ops.import_scene.gltf(filepath=str(R/'exports'/f'{name}.glb'));objs=list(set(scene.objects)-before)
 for o in objs:
  if o.type!='MESH':continue
  # Bake original imported transform before presentation-only layout.
  o.data=o.data.copy();o.data.transform(o.matrix_world);o.matrix_world=Matrix.Identity(4)
  if crop:
   cx,cy,w,d=crop;verts=[];faces=[];mats=[]
   for p in o.data.polygons:
    co=[o.data.vertices[i].co for i in p.vertices];center=sum(co,Vector())/len(co)
    if abs(center.x-cx)<w/2 and abs(center.y-cy)<d/2:
     ids=[]
     for v in co:ids.append(len(verts));verts.append((v.x-cx,v.y-cy,v.z))
     faces.append(ids);mats.append(p.material_index)
   mesh=bpy.data.meshes.new('actual city detail');mesh.from_pydata(verts,[],faces)
   for m in o.data.materials:mesh.materials.append(m)
   for p,mi in zip(mesh.polygons,mats):p.material_index=mi
   o.data=mesh
  o.rotation_mode='XYZ';o.rotation_euler=rot;o.scale=(scale,)*3;o.location=position
  if ghost:
   o.data.materials.clear();o.data.materials.append(cyan)
   for p in o.data.polygons:p.material_index=0
 return objs
label('AFTERLIGHT',-15,10.9,.82);label('THE COMPLETE LOW-POLY ASSET KIT',-15,10.15,.33,muted)
label('Actual exported geometry  /  presentation panels are NOT TO SCALE',-15,-11.25,.26,muted)
tile(-6,3.55,18.4,11.7);label('01  CITY NETWORK',-14.7,8.7,.40);label('25 primary junctions  /  2 hospitals  /  100 curb pickup anchors',-14.7,8.12,.25,muted)
load('city_static',(-5.7,3.1,0),.0082,(.55,0,.55))
tile(9.55,5.75,12.0,7.3);label('02  HERO AMBULANCE',4,8.7,.40);load('ambulance',(7.5,5.5,0),.82,(-.9,.50,.97));label('2,378 triangles',10.0,3.0,.25,muted)
tile(9.55,-.1,12.0,3.8);label('03  BASELINE GHOST',4,1.1,.34);load('ambulance',(7.1,-.55,0),.48,(-.95,.50,.97),True);label('Same mesh; cyan ghost material',10,-.1,.23,muted);label('Transparency applied in browser',10,-.55,.23,muted)
# lower fleet row
for name,x,title in [('car',-12.1,'CAR'),('truck',-6.8,'TRUCK'),('bike',-1.5,'BIKE')]:
 tile(x,-6.3,5.0,6.7);label(title,x-2.1,-3.65,.35);load(name,(x,-6,0),.72 if name!='bike' else 1.1,(-.9,.50,1.02))
tile(6.0,-6.3,8.9,6.7);label('BUILDING PALETTE',1.9,-3.65,.35)
for i,name in enumerate(['building_sand','building_slate','building_clay','building_sage']):
 objs=load(name,(2.8+i*1.8,-5.8,0),1.2,(-.8,.35,-.3))
 for o in objs:o.scale.z=2.0+(i%2)*.7
label('24 triangles / archetype',2,-9.1,.25,muted)
tile(13.0,-6.3,4.7,6.7);label('LANDMARKS',10.9,-3.65,.31)
m=json.loads((R/'map/city_manifest.json').read_text());h=next(b for b in m['buildings'] if b['kind']=='hospital')
load('city_static',(13,-5.9,0),.030,(-.85,.40,-.4),crop=(*h['center'],h['size'][0]+6,h['size'][1]+12));label('Hospital',11.05,-7.0,.25,muted)
p=next(p for p in m['parcels'] if p['kind']=='park');load('city_static',(13,-8.3,0),.012,(.6,0,-.3),crop=(*p['center'],*p['size']));label('Park + paths',11.05,-9.35,.25,muted)
bpy.ops.object.camera_add(location=(0,0,60));cam=bpy.context.object;cam.rotation_euler=(0,0,0);scene.camera=cam;cam.data.type='ORTHO';cam.data.ortho_scale=33;cam.data.clip_end=100
scene.render.engine='BLENDER_WORKBENCH';scene.display.shading.light='STUDIO';scene.display.shading.color_type='MATERIAL';scene.display.shading.show_shadows=False;scene.display.shading.show_cavity=True;scene.display.shading.cavity_type='BOTH';scene.display.shading.background_type='WORLD';scene.view_settings.view_transform='Standard'
scene.render.resolution_x=1920;scene.render.resolution_y=1440;scene.render.resolution_percentage=100;scene.render.filepath=str(R/'previews/asset_overview.png');bpy.ops.render.render(write_still=True)
print('Actual asset overview rendered without modifying frozen assets')
