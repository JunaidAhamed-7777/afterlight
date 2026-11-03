"""Recover authored buildings and add restrained three-dimensional detail.

Run with Blender 4.3.2 --background --python this_file -- --output-dir PATH.
Loads the original .blend read-only; never regenerates streets or edits the map.
Outputs go exclusively into a new, explicitly selected staging directory.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def bounds(points):
    return [[min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)]]


def components(mesh):
    parents = list(range(len(mesh.vertices)))
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for edge in mesh.edges:
        a, b = map(find, edge.vertices)
        if a != b:
            parents[b] = a
    groups = {}
    for poly in mesh.polygons:
        groups.setdefault(find(poly.vertices[0]), []).append(poly.index)
    return list(groups.values())


def owner_for(points, buildings):
    low, high = bounds(points)
    # All authored terrain, stripes and paths remain untouched ground geometry.
    if high[2] < .4:
        return None
    owners = []
    for b in buildings:
        x, y = b['center']; w, d = b['size']; h = b['height_m']
        if b['kind'] == 'hospital':
            # Existing main mass, smaller upper volume, entrance awning, glazing
            # and original H/MEDICAL lettering, all from the authored source.
            envelope = [x-w/2-1, x+w/2+1, y-d/2-9, y+d/2+1, h+8]
        else:
            # Existing source archetype roof overhang is 1.025 times footprint.
            envelope = [x-w*.513-0.02, x+w*.513+0.02,
                        y-d*.513-0.02, y+d*.513+0.02, h*1.04+.02]
        if (low[0] >= envelope[0] and high[0] <= envelope[1]
                and low[1] >= envelope[2] and high[1] <= envelope[3]
                and low[2] >= -.02 and high[2] <= envelope[4]):
            owners.append(b['id'])
    if len(owners) > 1:
        raise ValueError(f'Ambiguous original component ownership: {owners}')
    return owners[0] if owners else None


def append_box(vertices, faces, material_ids, center, size, material_index):
    x, y, z = center; w, d, h = (s/2 for s in size)
    start = len(vertices)
    vertices.extend([(x-w,y-d,z-h),(x+w,y-d,z-h),(x+w,y+d,z-h),(x-w,y+d,z-h),
                     (x-w,y-d,z+h),(x+w,y-d,z+h),(x+w,y+d,z+h),(x-w,y+d,z+h)])
    for face in ((0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)):
        faces.append(tuple(start+i for i in face)); material_ids.append(material_index)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    destinations = [output/'city_enhanced.glb', output/'afterlight_city_enhanced.blend', output/'city_enhanced_manifest.json']
    if any(path.exists() for path in destinations):
        raise ValueError('Staged output exists; select a fresh output directory')
    source = ROOT/'afterlight_city.blend'; canonical = ROOT/'map/city_manifest.json'
    provenance = {'source_blend_sha256': sha(source), 'canonical_map_sha256': sha(canonical),
                  'generator_sha256': sha(Path(__file__)), 'blender_version': bpy.app.version_string}
    bpy.ops.wm.open_mainfile(filepath=str(source))
    graph = json.loads(canonical.read_text())
    original = bpy.data.objects['city_static_batched']
    source_mesh = original.data
    root_matrix = original.matrix_world.copy()
    world_vertices = [tuple(root_matrix @ v.co) for v in source_mesh.vertices]
    ownership = {b['id']: [] for b in graph['buildings']}
    ownership['GROUND'] = []
    for group in components(source_mesh):
        ids = {v for index in group for v in source_mesh.polygons[index].vertices}
        owner = owner_for([world_vertices[i] for i in ids], graph['buildings'])
        ownership[owner or 'GROUND'].extend(group)
    if sum(map(len, ownership.values())) != len(source_mesh.polygons):
        raise ValueError('Original face ownership is incomplete')
    if any(not ownership[b['id']] for b in graph['buildings']):
        raise ValueError('A canonical building has no recovered original faces')
    material_slots = list(source_mesh.materials)
    glass = next(i for i,m in enumerate(material_slots) if m.name.startswith('glass'))
    porcelain = next(i for i,m in enumerate(material_slots) if m.name.startswith('porcelain'))
    build_collection = bpy.data.collections.new('AFTERLIGHT_CITY_ENHANCED')
    bpy.context.scene.collection.children.link(build_collection)
    root = bpy.data.objects.new('AFTERLIGHT_CITY', None)
    build_collection.objects.link(root); root.matrix_world = root_matrix
    root['canonical_map_sha256'] = provenance['canonical_map_sha256']
    root['preserved_authored_root'] = True
    root['coordinate_system'] = 'Blender XY meters, Z up; glTF [x,z,-y]'
    node_manifest = []
    by_id = {b['id']: b for b in graph['buildings']}
    added_faces = 0
    for identifier, indices in ownership.items():
        used = sorted({v for index in indices for v in source_mesh.polygons[index].vertices})
        remap = {old:i for i,old in enumerate(used)}
        vertices = [tuple(source_mesh.vertices[i].co) for i in used]
        faces = [tuple(remap[v] for v in source_mesh.polygons[i].vertices) for i in indices]
        materials = [source_mesh.polygons[i].material_index for i in indices]
        original_faces = len(faces)
        detail_porcelain = next((slot for slot in materials if material_slots[slot].name.startswith('porcelain')), porcelain)
        detail_style = 'original_landmark'
        if identifier != 'GROUND' and by_id[identifier]['kind'] != 'hospital':
            b = by_id[identifier]; x,y = b['center']; w,d = b['size']; h=b['height_m']
            inverse = root_matrix.inverted()
            def box(center,size,material):
                append_box(vertices,faces,materials,tuple(inverse@Vector(center)),size,material)
            # Real shallow bay volumes, no decal/billboard texture, proportioned
            # for close camera views without tiny geometry on every storey.
            floors = 3 if h >= 27 else 2
            for level in range(floors):
                z = h*(.25 + .55*level/max(1,floors-1))
                wh = min(2.4,h*.10)
                for side in (-1,1):
                    for fraction in (-.29,0,.29):
                        box((x+w*fraction,y+side*(d/2+.10),z),(w*.18,.24,wh),glass)
                    for fraction in (-.25,.25):
                        box((x+side*(w/2+.10),y+d*fraction,z),(.24,d*.25,wh),glass)
            # Four slim architectural ledges create genuine side silhouettes.
            for side in (-1,1):
                box((x,y+side*(d/2+.10),h*.14),(w*.98,.32,.30),detail_porcelain)
                box((x+side*(w/2+.10),y,h*.14),(.32,d*.98,.30),detail_porcelain)
            # Small inset rooftop service volume, within parcel XY footprint.
            # Main authored mass and cap remain untouched; actual new bounds
            # explicitly include the extra 0.8–1.8 m rooftop silhouette.
            roof_h=min(1.8,max(.8,h*.045))
            box((x+w*.12,y-d*.10,h*1.03+roof_h/2),(w*.38,d*.32,roof_h),detail_porcelain)
            detail_style='shallow_3d_bays_ledges_rooftop'
        added_faces += len(faces)-original_faces
        mesh=bpy.data.meshes.new(f'{identifier}_authored_detail_mesh'); mesh.from_pydata(vertices,[],faces); mesh.update()
        # Compact material slots per node to avoid exporting unused references.
        slots=[]; mapped={}; identity_slots={}
        for slot in sorted(set(materials)):
            identity=material_slots[slot].as_pointer()
            if identity not in identity_slots:
                identity_slots[identity]=len(slots); slots.append(slot)
                mesh.materials.append(material_slots[slot])
            mapped[slot]=identity_slots[identity]
        for poly,slot in zip(mesh.polygons,materials): poly.material_index=mapped[slot]
        name='AL_GROUND' if identifier=='GROUND' else f'AL_BUILDING_{identifier}'
        obj=bpy.data.objects.new(name,mesh); build_collection.objects.link(obj); obj.parent=root; obj.matrix_basis=Matrix.Identity(4)
        obj['occluder']=identifier!='GROUND'; obj['source_faces_preserved']=original_faces
        if identifier!='GROUND': obj['building_id']=identifier
        if identifier!='GROUND':
            low,high=bounds([tuple(root_matrix@Vector(v)) for v in vertices])
            render_low=[low[0],low[2],-high[1]]; render_high=[high[0],high[2],-low[1]]
            node_manifest.append({'building_id':identifier,'node_name':name,'kind':by_id[identifier]['kind'],
                                  'canonical_body_height_m':by_id[identifier]['height_m'],
                                  'world_bounds_blender_m':[low,high],'world_bounds_render_m':[render_low,render_high],
                                  'original_faces':original_faces,'added_faces':len(faces)-original_faces,'detail_style':detail_style})
    # Hide original source collections without deleting their authored content.
    for collection in bpy.data.collections:
        if collection!=build_collection: collection.hide_render=True
    bpy.ops.object.select_all(action='DESELECT')
    for obj in build_collection.objects: obj.select_set(True)
    bpy.context.view_layer.objects.active=root
    bpy.ops.export_scene.gltf(filepath=str(destinations[0]),export_format='GLB',use_selection=True,
                              export_yup=True,export_extras=True,export_materials='EXPORT')
    bpy.ops.wm.save_as_mainfile(filepath=str(destinations[1]))
    report={'schema':'afterlight.city-enhancement.v1','provenance':provenance,
            'asset':destinations[0].name,'asset_bytes':destinations[0].stat().st_size,'asset_sha256':sha(destinations[0]),
            'source_original_faces':len(source_mesh.polygons),'added_faces':added_faces,
            'root_blender_translation_m':list(root_matrix.translation),'root_render_translation_m':[root_matrix.translation.x,root_matrix.translation.z,-root_matrix.translation.y],
            'building_count':len(node_manifest),'buildings':node_manifest,'ground_node':'AL_GROUND',
            'ground_original_faces':len(ownership['GROUND']),'canonical_geometry_changed':False,
            'vehicle_geometry_changed':False,
            'material_policy':'shared_immutable_asset_materials; preserve palette and glass; renderer must isolate building fade from ground, using per-building clones or per-vertex building masks',
            'validation_status':'build_only_omen_visual_and_runtime_validation_pending',
            'notes':'Original source faces retained exactly once. New building details only; rooftop volume expands visual Z bounds. No render or simulation executed.'}
    destinations[2].write_text(json.dumps(report,indent=2)+'\n')
    print('BUILD_OUTPUT='+json.dumps({k:v for k,v in report.items() if k!='buildings'}))


if __name__=='__main__': main()
