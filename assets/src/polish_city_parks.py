import bpy,json,pathlib,math
R=pathlib.Path(__file__).resolve().parents[1]
m=json.loads((R/'map/city_manifest.json').read_text());col=bpy.data.collections['city_static'];created=[]
def adopt(o,mat):
 for c in list(o.users_collection):c.objects.unlink(o)
 col.objects.link(o);o.data.materials.append(bpy.data.materials[mat]);created.append(o)
def box(pos,size):
 bpy.ops.mesh.primitive_cube_add(size=1,location=pos);o=bpy.context.object;adopt(o,'sidewalk');o.scale=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
for p in m['parcels']:
 if p['kind']!='park':continue
 x,y=p['center'];w,d=p['size'];box((x,y,.18),(w*.92,3,.1));box((x,y,.18),(3,d*.92,.1))
 for ix in [-.35,-.12,.12,.35]:
  for iy in [-.32,.32]:
   xx=x+w*ix;yy=y+d*iy
   bpy.ops.mesh.primitive_cylinder_add(vertices=6,radius=.7,depth=4,location=(xx,yy,2));adopt(bpy.context.object,'terracotta')
   bpy.ops.mesh.primitive_cone_add(vertices=7,radius1=5,radius2=1.1,depth=10,location=(xx,yy,8));adopt(bpy.context.object,'mint')
# Merge décor into existing city root to keep shared draw batches.
bpy.ops.object.select_all(action='DESELECT')
for o in col.objects:o.select_set(True)
bpy.context.view_layer.objects.active=bpy.data.objects['city_static_batched'];bpy.ops.object.join()
bpy.ops.export_scene.gltf(filepath=str(R/'exports/city_static.glb'),export_format='GLB',use_selection=True,export_yup=True,export_extras=True)
sc=bpy.context.scene;sc.render.engine='BLENDER_WORKBENCH';sc.display.shading.color_type='MATERIAL';sc.display.shading.show_cavity=True;sc.display.shading.show_shadows=True;sc.view_settings.view_transform='Standard';sc.view_settings.look='None';sc.view_settings.exposure=.35;sc.camera.data.clip_end=5000;sc.render.filepath=str(R/'previews/city_overview.png');bpy.ops.render.render(write_still=True);bpy.ops.wm.save_as_mainfile(filepath=str(R/'afterlight_city.blend'))
print('Two parks receive sparse low-poly trees and paths; brighter city preview saved')
