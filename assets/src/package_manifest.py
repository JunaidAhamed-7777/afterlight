import pathlib,json,hashlib,struct
root=pathlib.Path(__file__).resolve().parents[1]
rows=[]
for p in sorted((root/'exports').glob('*.glb')):
 b=p.read_bytes();j=json.loads(b[20:20+struct.unpack_from('<I',b,12)[0]])
 tris=sum(j['accessors'][pr.get('indices',pr['attributes']['POSITION'])]['count']//3 for m in j.get('meshes',[]) for pr in m['primitives'])
 rows.append({'file':str(p.relative_to(root)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'mesh_triangles':tris,'materials':len(j.get('materials',[])),'textures':len(j.get('textures',[])),'source':'original procedural Blender geometry','external_assets':False})
out={'schema':'afterlight.assets.v1','authoring':'Blender 4.3.2 through pinned Blender MCP','rights':'original geometry for repository owner; project license to be selected by owner','source_front_axis':'+Y','export_front_axis':'-Z','export_up_axis':'+Y','units':'meters','files':rows,'total_glb_bytes':sum(r['bytes'] for r in rows),'status':'asset exports; no simulated benchmark or browser performance claim'}
(root/'asset_manifest.json').write_text(json.dumps(out,indent=2))
print(out['total_glb_bytes'],len(rows))
