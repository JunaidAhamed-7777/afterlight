"""Afterlight original procedural assets. Execute through pinned Blender MCP.
Meters, Z up, vehicle front +Y. Ground-centered origins export to glTF front -Z.
No textures or external assets. Generated for Junaid Ahamed's Afterlight.
"""
import bpy, math, json, pathlib
from mathutils import Vector
ROOT=pathlib.Path(__file__).resolve().parents[1]
for o in list(bpy.data.objects): bpy.data.objects.remove(o,do_unlink=True)
for c in list(bpy.data.collections):
 if c.name!='Collection': bpy.data.collections.remove(c)
M={}
def mat(name,color,metal=0,rough=.6,emission=0,alpha=1):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,alpha);m.use_nodes=True
 p=m.node_tree.nodes.get('Principled BSDF');p.inputs['Base Color'].default_value=(*color,alpha);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough;p.inputs['Alpha'].default_value=alpha
 if emission:p.inputs['Emission Color'].default_value=(*color,1);p.inputs['Emission Strength'].default_value=emission
 if alpha<1:m.surface_render_method='DITHERED'
 M[name]=m;return m
mat('porcelain',(.88,.90,.84));mat('amber',(.99,.48,.105));mat('navy',(.035,.09,.14));mat('glass',(.035,.23,.30),.25,.22);mat('rubber',(.025,.035,.045));mat('alloy',(.40,.49,.50),.65,.32);mat('beacon_cyan',(.035,.48,.8),emission=.35);mat('lamp',(.64,.92,1),emission=2);mat('redlamp',(.8,.10,.06),emission=1);mat('mint',(.25,.65,.55));mat('terracotta',(.58,.28,.20));mat('bluegrey',(.30,.44,.52));mat('cream',(.63,.57,.43));mat('ghost',(.20,.72,1),rough=.4,emission=.8,alpha=.28)
active=None
def collection(name):
 global active
 active=bpy.data.collections.new(name);bpy.context.scene.collection.children.link(active);return active

def adopt(o,name,material):
 o.name=name
 for c in list(o.users_collection):c.objects.unlink(o)
 active.objects.link(o)
 if material:o.data.materials.append(M[material])
 return o

def box(name,pos,size,material,bevel=0):
 bpy.ops.mesh.primitive_cube_add(size=1,location=pos);o=adopt(bpy.context.object,name,material);o.scale=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
 if bevel:
  mod=o.modifiers.new('soft silhouette','BEVEL');mod.width=bevel;mod.segments=1;bpy.context.view_layer.objects.active=o;bpy.ops.object.modifier_apply(modifier=mod.name)
 return o

def cyl(name,pos,radius,depth,material,vertices=12,rot=(0,0,0)):
 bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=depth,location=pos,rotation=rot);return adopt(bpy.context.object,name,material)

def mesh(name,verts,faces,material):
 me=bpy.data.meshes.new(name);me.from_pydata(verts,[],faces);me.update();o=bpy.data.objects.new(name,me);active.objects.link(o);o.data.materials.append(M[material]);return o

def wheels(wheelbase,halfwidth,r,z,detail=False):
 for y in [-wheelbase/2,wheelbase/2]:
  for x in [-halfwidth,halfwidth]:
   cyl('tire',(x,y,z),r,.23,'rubber',16 if detail else 10,(0,math.pi/2,0))
   cyl('hub',(x+(.125 if x>0 else -.125),y,z),r*.59,.025,'alloy',12 if detail else 8,(0,math.pi/2,0))
   if detail:
    cyl('hub center',(x+(.145 if x>0 else -.145),y,z),r*.22,.035,'navy',8,(0,math.pi/2,0))

def text(name,body,pos,size,material,rot=(0,0,0)):
 cu=bpy.data.curves.new(name,'FONT');cu.body=body;cu.size=size;cu.align_x='CENTER';cu.align_y='CENTER';cu.extrude=.001;cu.resolution_u=1
 o=bpy.data.objects.new(name,cu);active.objects.link(o);o.location=pos;o.rotation_euler=rot;cu.materials.append(M[material]);bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o.select_set(False);return o

# Hero ambulance: forward +Y, ground origin, distinctive compact rescue van.
collection('ambulance')
box('underbody',(0,0,.61),(1.93,4.85,.35),'navy',.10)
box('medical cabin',(0,-.75,1.63),(2.08,3.4,2.05),'porcelain',.13)
box('cab lower',(0,1.64,1.0),(1.98,1.6,.74),'porcelain',.13)
# Tapered cab roof and sloped windshield.
verts=[(-.98,.9,1.25),(.98,.9,1.25),(.98,2.42,1.25),(-.98,2.42,1.25),(-.89,.9,2.46),(.89,.9,2.46),(.89,1.98,2.46),(-.89,1.98,2.46)]
mesh('cab shell',verts,[(0,1,2,3),(4,7,6,5),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)],'porcelain')
mesh('panoramic windshield',[(-.79,2.012,2.38),(.79,2.012,2.38),(.85,2.31,1.58),(-.85,2.31,1.58)],[(0,1,2,3)],'glass')
box('windshield divider',(0,2.16,1.98),(.035,.035,.81),'navy').rotation_euler.x=.36
for side in [-1,1]:
 x=side*1.045
 box('rescue stripe',(x,-.64,1.29),(.014,3.27,.30),'amber')
 box('lower skirt',(x,-.65,.79),(.025,3.28,.14),'navy')
 mesh('cab side window',[(side*.986,1.00,1.57),(side*.986,2.25,1.57),(side*.90,1.95,2.33),(side*.90,1.00,2.33)],[(0,1,2,3)],'glass')
 box('cab door seam',(side*1.003,1.02,1.03),(.014,.025,.48),'navy')
 box('door pull',(side*1.025,1.22,1.45),(.055,.25,.065),'navy',.015)
 box('mirror arm',(side*1.13,1.96,1.68),(.30,.06,.06),'navy')
 box('wing mirror',(side*1.27,1.94,1.79),(.12,.24,.32),'navy',.025)
 box('medical window',(side*1.052,-.60,2.14),(.016,1.28,.51),'glass',.06)
 # Original pulse symbol, deliberately not a red cross.
 for yy,zz,ang in [(-1.94,1.80,0),(-1.75,1.87,.65),(-1.57,1.78,-.75),(-1.37,1.82,.35)]:
  o=box('pulse identity',(side*1.064,yy,zz),(.025,.23,.055),'amber');o.rotation_euler.x=ang
 box('side access panel',(side*1.058,-1.78,1.05),(.016,.66,.28),'porcelain',.015)
 box('rear latch',(side*1.07,-2.10,1.06),(.03,.10,.035),'alloy')
# face and rear details
box('front grille',(0,2.457,.99),(.94,.055,.27),'navy',.035)
for x in [-.66,.66]:box('headlamp',(x,2.456,1.18),(.38,.07,.20),'lamp',.035)
box('front bumper',(0,2.51,.70),(1.99,.17,.19),'navy',.035)
box('rear step',(0,-2.52,.61),(1.78,.22,.12),'alloy',.03)
box('rear door split',(0,-2.459,1.70),(.025,.025,1.69),'navy')
for x in [-.52,.52]:
 box('rear window',(x,-2.469,2.12),(.71,.025,.53),'glass',.04)
 box('rear handle',(x*.37,-2.486,1.51),(.06,.045,.25),'navy',.01)
 box('tail lamp',(x*1.75,-2.475,1.06),(.15,.05,.38),'redlamp',.025)
box('rear stripe',(0,-2.475,1.30),(1.83,.025,.21),'amber')
box('roof base',(0,.87,2.57),(1.65,.40,.10),'navy',.03)
for x in [-.59,.59]:box('lightbar lens',(x,.87,2.68),(.48,.32,.15),'beacon_cyan',.04)
box('roof ventilation',(0,-1.15,2.71),(.75,.85,.15),'porcelain',.06)
for y in [-1.38,-1.18,-.98]:box('vent slot',(0,y,2.79),(.55,.035,.008),'navy')
wheels(3.25,1.00,.43,.44,True)
text('roof ambulance label','AMBULANCE',(0,-.15,2.67),.22,'navy')
# Export meshes join per archetype, retaining material slots (later browser batch by palette).
def export(name):
 objs=list(active.objects)
 bpy.ops.object.select_all(action='DESELECT')
 for o in objs:o.select_set(True)
 bpy.context.view_layer.objects.active=objs[0];bpy.ops.object.join();o=bpy.context.object;o.name=name
 bpy.context.scene.cursor.location=(0,0,0);bpy.ops.object.origin_set(type='ORIGIN_CURSOR');o['source_front_axis']='+Y';o['front_axis']='-Z';o['up_axis']='+Y';o['units']='meters';o['origin']='ground center'
 bpy.ops.export_scene.gltf(filepath=str(ROOT/'exports'/f'{name}.glb'),export_format='GLB',use_selection=True,export_yup=True,export_materials='EXPORT',export_extras=True)
 return o
hero=export('ambulance')
# Civilian assets use bounded primitive silhouettes.
for kind,color in [('car','bluegrey'),('truck','cream'),('bike','terracotta')]:
 collection(kind)
 if kind=='car':
  box('body',(0,0,.65),(1.74,3.95,.61),color,.10);box('cabin',(0,-.12,1.17),(1.46,1.95,.70),'glass',.09);box('roof',(0,-.19,1.56),(1.42,1.64,.10),color,.04);wheels(2.55,.83,.31,.32)
  for x in [-.56,.56]:box('front light',(x,1.99,.70),(.30,.025,.13),'lamp')
 elif kind=='truck':
  box('chassis',(0,0,.67),(1.95,5.4,.27),'navy');box('cargo',(0,-.75,1.54),(2.04,3.9,1.65),color,.05);box('cab',(0,1.92,1.30),(1.95,1.45,1.57),'porcelain',.08);box('windshield',(0,2.66,1.65),(1.67,.025,.61),'glass');wheels(3.70,.96,.40,.41)
 else:
  for y in [-.72,.72]:cyl('wheel',(0,y,.30),.30,.12,'rubber',10,(0,math.pi/2,0))
  box('frame',(0,0,.52),(.20,1.40,.14),'navy');box('seat',(0,-.24,.78),(.43,.70,.13),'navy',.04);box('tank',(0,.25,.72),(.38,.50,.35),color,.05);box('handlebar',(0,.61,1.05),(.76,.08,.08),'alloy');box('front light',(0,.76,.86),(.20,.10,.17),'lamp')
 export(kind)
# Shared building modules, scaled by manifest. Recognizable palette without texture payload.
for kind,material in [('building_sand','cream'),('building_slate','bluegrey'),('building_clay','terracotta'),('building_sage','mint')]:
 collection(kind);box('volume',(0,0,.5),(1,1,1),material);box('roof',(0,0,1.015),(1.025,1.025,.03),'porcelain');export(kind)
# Preview scene; hide archetypes except hero. No stage in exported models.
for col in bpy.data.collections:
 if col.name not in ['ambulance','Collection']:col.hide_render=True
collection('preview_stage')
box('pedestal',(0,0,-.16),(7.0,8.0,.28),'navy',.15)
mat('stage',(.11,.16,.21));box('floor',(0,0,-.4),(200,200,.2),'stage')
world=bpy.context.scene.world or bpy.data.worlds.new('Studio');bpy.context.scene.world=world;world.use_nodes=True;world.node_tree.nodes['Background'].inputs[0].default_value=(.19,.24,.32,1);world.node_tree.nodes['Background'].inputs[1].default_value=.45
for name,pos,power,size in [('key',(4,1,8),1600,6),('rim',(-4,-4,6),1800,5),('fill',(0,6,4),900,4)]:
 bpy.ops.object.light_add(type='AREA',location=pos);o=adopt(bpy.context.object,name,None);o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(Vector((0,0,1))-o.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.camera_add(location=(8,10,7));cam=adopt(bpy.context.object,'hero camera',None);cam.rotation_euler=(Vector((0,0,1.2))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=8.5;bpy.context.scene.camera=cam
sc=bpy.context.scene;sc.render.engine='BLENDER_EEVEE_NEXT';sc.render.film_transparent=False;sc.render.resolution_x=1200;sc.render.resolution_y=1000;sc.render.resolution_percentage=100;sc.view_settings.view_transform='AgX'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'afterlight_assets.blend'))
sc.render.filepath=str(ROOT/'previews/ambulance_front.png');bpy.ops.render.render(write_still=True)
print('ASSETS GENERATED AND HERO PREVIEW RENDERED')
