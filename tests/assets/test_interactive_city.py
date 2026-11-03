"""Structural/geometry checks for the real enhanced city; run on Omen only.

No rendering/FPS/occlusion-quality claim follows from these binary checks.
Missing staged or published assets are failures, never skipped validation.
Set AFTERLIGHT_CITY_ASSET to deliberately inspect an alternate staged GLB;
its sibling <stem>_manifest.json is then required.
"""
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import unittest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT/'assets'
CITY = Path(os.environ.get('AFTERLIGHT_CITY_ASSET', str(ASSETS/'exports/city_enhanced.glb')))
MANIFEST = CITY.with_name(CITY.stem+'_manifest.json')
MAX_BYTES = 25_000_000
ORIGINAL_HASHES = {
    'map/city_manifest.json':'87274a02fa237234f09a230cda5457a2c8a2c983a5541fe43378ced6cc16781b',
    'exports/city_instances.json':'2a51e8181a9dfdb8bab45a1614d729a247c227cce5951670fd7a26c85af7a9f5',
    'exports/city_static.glb':'31536f9bf0ca0c1f6aebfa959792cb39058068ab8594e35744235451fe510efe',
    'exports/ambulance.glb':'df7d3162d5f7f377ed9b56ef53c104233877208795fafaddc06871d420388af1',
    'exports/car.glb':'a6021c89611c079f642e36d7daa534cacea9d224cbe1ad747f54c0a620adf591',
    'exports/truck.glb':'7d7483075d1b716f4d808dc964b426f1ef86e609a8187ae927d95935b2d799b4',
    'exports/bike.glb':'ccd19f98a55621bfa19c52fa89b19ed018c001e2a9f8f8208cd2ab78358f8236',
}


def load_glb(path):
    raw=path.read_bytes()
    if len(raw)<20:raise ValueError('GLB is truncated')
    magic,version,length=struct.unpack_from('<4sII',raw)
    if magic!=b'glTF' or version!=2 or length!=len(raw):raise ValueError('Invalid GLB header/version/length')
    chunks=[];offset=12
    while offset<len(raw):
        if offset+8>len(raw):raise ValueError('Truncated GLB chunk header')
        size,kind=struct.unpack_from('<II',raw,offset);offset+=8
        if size%4 or offset+size>len(raw):raise ValueError('Invalid GLB chunk bounds/alignment')
        chunks.append((kind,raw[offset:offset+size]));offset+=size
    if [kind for kind,_ in chunks]!=[0x4E4F534A,0x004E4942]:raise ValueError('Expected one JSON and one embedded BIN chunk')
    document=json.loads(chunks[0][1].decode('utf-8'))
    return raw,document,chunks[1][1]


def accessor(document,binary,index):
    a=document['accessors'][index]
    if 'sparse' in a:raise ValueError('Unexpected sparse accessor in authored city')
    formats={5120:'b',5121:'B',5122:'h',5123:'H',5125:'I',5126:'f'}
    components={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
    fmt='<'+formats[a['componentType']]*components[a['type']]
    size=struct.calcsize(fmt)
    view=document['bufferViews'][a['bufferView']]
    if view['buffer']!=0:raise ValueError('External or unexpected buffer')
    start=view.get('byteOffset',0)+a.get('byteOffset',0)
    stride=view.get('byteStride',size)
    count=a['count']
    if not isinstance(count,int) or isinstance(count,bool) or count<=0 or stride<size:raise ValueError('Invalid accessor count/stride')
    stop=start+(count-1)*stride+size
    if start<view.get('byteOffset',0) or stop>view.get('byteOffset',0)+view['byteLength'] or stop>len(binary):
        raise ValueError('Accessor escapes its buffer view')
    values=[struct.unpack_from(fmt,binary,start+i*stride) for i in range(count)]
    if any(not math.isfinite(value) for row in values for value in row):raise ValueError('Nonfinite geometry/accessor value')
    return values


def multiply(a,b):
    return [[sum(a[r][k]*b[k][c] for k in range(4)) for c in range(4)] for r in range(4)]


def matrix(node):
    if 'matrix' in node:
        values=node['matrix']
        if len(values)!=16:raise ValueError('Invalid node matrix')
        return [[values[c*4+r] for c in range(4)] for r in range(4)]
    x,y,z,w=node.get('rotation',[0,0,0,1])
    sx,sy,sz=node.get('scale',[1,1,1]);tx,ty,tz=node.get('translation',[0,0,0])
    return [[(1-2*(y*y+z*z))*sx,2*(x*y-z*w)*sy,2*(x*z+y*w)*sz,tx],
            [2*(x*y+z*w)*sx,(1-2*(x*x+z*z))*sy,2*(y*z-x*w)*sz,ty],
            [2*(x*z-y*w)*sx,2*(y*z+x*w)*sy,(1-2*(x*x+y*y))*sz,tz],[0,0,0,1]]


def point(transform,position):
    return tuple(sum(transform[r][k]*position[k] for k in range(3))+transform[r][3] for r in range(3))


def area_squared(a,b,c):
    u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
    cross=(u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0])
    return sum(value*value for value in cross)/4


class InteractiveCityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw,cls.gltf,cls.binary=load_glb(CITY)
        cls.report=json.loads(MANIFEST.read_text(encoding='utf-8'))
        cls.graph=json.loads((ASSETS/'map/city_manifest.json').read_text(encoding='utf-8'))
        cls.nodes=cls.gltf['nodes']
        cls.buildings={node.get('extras',{}).get('building_id'):node for node in cls.nodes if 'building_id' in node.get('extras',{})}

    def test_original_city_graph_and_tiny_vehicle_bytes_unchanged(self):
        for relative,expected in ORIGINAL_HASHES.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ASSETS/relative).read_bytes()).hexdigest(),expected)

    def test_file_budget_and_exact_manifest_binding(self):
        self.assertGreater(len(self.raw),1000)
        self.assertLessEqual(len(self.raw),MAX_BYTES)
        self.assertEqual(self.report['schema'],'afterlight.city-enhancement.v1')
        self.assertEqual(self.report['asset'],CITY.name)
        self.assertEqual(self.report['asset_bytes'],len(self.raw))
        self.assertEqual(self.report['asset_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertIs(self.report['canonical_geometry_changed'],False)
        self.assertIs(self.report['vehicle_geometry_changed'],False)
        self.assertEqual(self.report['provenance']['canonical_map_sha256'],ORIGINAL_HASHES['map/city_manifest.json'])

    def test_embedded_real_meshes_not_external_textures_or_billboard_scene(self):
        self.assertEqual(self.gltf['asset']['version'],'2.0')
        self.assertEqual(len(self.gltf['buffers']),1)
        self.assertNotIn('uri',self.gltf['buffers'][0])
        self.assertLessEqual(self.gltf['buffers'][0]['byteLength'],len(self.binary))
        self.assertLess(len(self.binary)-self.gltf['buffers'][0]['byteLength'],4)
        self.assertFalse(self.gltf.get('images',[]))
        self.assertFalse(self.gltf.get('textures',[]))
        self.assertFalse(self.gltf.get('animations',[]))
        self.assertFalse(self.gltf.get('skins',[]))
        self.assertGreater(len(self.gltf['meshes']),len(self.buildings))
        for index in range(len(self.gltf['accessors'])):
            with self.subTest(accessor=index):accessor(self.gltf,self.binary,index)

    def test_stable_complete_ids_and_single_mesh_ownership(self):
        expected={building['id'] for building in self.graph['buildings']}
        listed=[node['extras']['building_id'] for node in self.nodes if 'building_id' in node.get('extras',{})]
        self.assertEqual(len(expected),187)
        self.assertEqual(set(listed),expected)
        self.assertEqual(len(listed),len(expected),'Duplicate building IDs must not be hidden by dict collapse')
        self.assertEqual({item['building_id'] for item in self.report['buildings']},expected)
        self.assertEqual(len(self.report['buildings']),len(expected))
        self.assertEqual(self.report['building_count'],len(expected))
        owned=[]
        for identifier,node in self.buildings.items():
            self.assertEqual(node['name'],'AL_BUILDING_'+identifier)
            self.assertIs(node['extras']['occluder'],True)
            self.assertGreater(node['extras']['source_faces_preserved'],0)
            owned.append(node['mesh'])
        ground=[node for node in self.nodes if node.get('name')=='AL_GROUND']
        self.assertEqual(len(ground),1)
        self.assertIs(ground[0]['extras']['occluder'],False)
        self.assertNotIn('building_id',ground[0]['extras'])
        for node in self.nodes:
            if 'mesh' in node and 'building_id' not in node.get('extras',{}):
                self.assertEqual(node.get('name'),'AL_GROUND','Unclassified geometry must not enter localized building fading')
                self.assertIs(node.get('extras',{}).get('occluder'),False)
        self.assertEqual(len(set([*owned,ground[0]['mesh']])),len(owned)+1)
        uses=Counter(node['mesh'] for node in self.nodes if 'mesh' in node)
        self.assertTrue(all(uses[mesh]==1 for mesh in owned),'Building meshes cannot be reused by unrelated scene nodes')

    def test_authored_root_and_children_transforms_preserved(self):
        roots=self.gltf['scenes'][self.gltf.get('scene',0)]['nodes']
        self.assertEqual(len(roots),1)
        root=self.nodes[roots[0]]
        self.assertEqual(root['name'],'AFTERLIGHT_CITY')
        self.assertEqual(root.get('translation'),[10,-3,-7.5])
        self.assertIs(root['extras']['preserved_authored_root'],True)
        self.assertEqual(root['extras']['canonical_map_sha256'],ORIGINAL_HASHES['map/city_manifest.json'])
        self.assertEqual(self.report['root_render_translation_m'],[10,-3,-7.5])
        expected_children={i for i,node in enumerate(self.nodes) if 'mesh' in node}
        self.assertEqual(set(root['children']),expected_children)
        self.assertEqual(len(root['children']),len(expected_children))
        identity=matrix({})
        for index in root['children']:
            self.assertEqual(matrix(self.nodes[index]),identity,'Geometry must remain authored root-local, not double-transformed')

    def test_finite_volumetric_building_triangles_and_reported_world_bounds(self):
        root=self.nodes[self.gltf['scenes'][self.gltf.get('scene',0)]['nodes'][0]]
        reports={item['building_id']:item for item in self.report['buildings']}
        canonical={item['id']:item for item in self.graph['buildings']}
        total_triangles=0
        for identifier,node in self.buildings.items():
            with self.subTest(building=identifier):
                transform=multiply(matrix(root),matrix(node))
                positions=[];nondegenerate=0;building_triangles=0
                mesh=self.gltf['meshes'][node['mesh']]
                self.assertTrue(mesh['primitives'])
                for primitive in mesh['primitives']:
                    self.assertEqual(primitive.get('mode',4),4)
                    self.assertFalse(primitive.get('targets',[]))
                    self.assertIn('POSITION',primitive['attributes'])
                    source=accessor(self.gltf,self.binary,primitive['attributes']['POSITION'])
                    self.assertTrue(all(len(p)==3 for p in source))
                    converted=[point(transform,p) for p in source];positions.extend(converted)
                    indices=[v[0] for v in accessor(self.gltf,self.binary,primitive['indices'])] if 'indices' in primitive else list(range(len(source)))
                    self.assertEqual(len(indices)%3,0)
                    self.assertTrue(all(isinstance(i,int) and 0<=i<len(source) for i in indices))
                    total_triangles+=len(indices)//3
                    building_triangles+=len(indices)//3
                    nondegenerate+=sum(area_squared(*(converted[indices[i+j]] for j in range(3)))>1e-12 for i in range(0,len(indices),3))
                self.assertGreaterEqual(nondegenerate,12,'Not a volumetric authored building')
                self.assertGreaterEqual(building_triangles,reports[identifier]['original_faces']+reports[identifier]['added_faces'],
                                        'Declared polygon detail must exist as actual triangle geometry')
                low=[min(p[axis] for p in positions) for axis in range(3)]
                high=[max(p[axis] for p in positions) for axis in range(3)]
                self.assertTrue(all(high[i]-low[i]>1 for i in range(3)))
                authored=canonical[identifier]
                x,y=authored['center'];width,depth=authored['size']
                self.assertLessEqual(low[0],x);self.assertGreaterEqual(high[0],x)
                self.assertLessEqual(low[2],-y);self.assertGreaterEqual(high[2],-y)
                self.assertGreaterEqual(high[0]-low[0],width-.005)
                self.assertGreaterEqual(high[2]-low[2],depth-.005)
                self.assertGreaterEqual(high[1]-low[1],authored['height_m']-.005)
                self.assertEqual(reports[identifier]['canonical_body_height_m'],authored['height_m'])
                declared=reports[identifier]['world_bounds_render_m']
                for measured,expected in zip([*low,*high],[*declared[0],*declared[1]]):
                    self.assertAlmostEqual(measured,expected,delta=.005)
        self.assertGreater(total_triangles,0)

    def test_material_references_are_valid_and_asset_materials_remain_opaque(self):
        # Sharing immutable GLB materials is intentional. The viewer must use
        # per-building clones OR localized per-vertex masks, never fade shared
        # ground material globally; runtime isolation needs browser QA.
        materials=self.gltf['materials']
        self.assertTrue(materials)
        for node in self.buildings.values():
            for primitive in self.gltf['meshes'][node['mesh']]['primitives']:
                self.assertIsInstance(primitive['material'],int)
                self.assertTrue(0<=primitive['material']<len(materials))
                material=materials[primitive['material']]
                self.assertEqual(material.get('alphaMode','OPAQUE'),'OPAQUE')
                rgba=material.get('pbrMetallicRoughness',{}).get('baseColorFactor',[1,1,1,1])
                self.assertEqual(len(rgba),4)
                self.assertTrue(all(math.isfinite(x) and 0<=x<=1 for x in rgba))
                self.assertEqual(rgba[3],1)

    def test_original_face_inventory_and_added_real_detail_declared(self):
        self.assertEqual(self.report['source_original_faces'],7360)
        self.assertEqual(self.report['ground_original_faces'],4516)
        self.assertEqual(sum(row['original_faces'] for row in self.report['buildings'])+self.report['ground_original_faces'],7360)
        self.assertGreater(self.report['added_faces'],0)
        self.assertEqual(sum(row['added_faces'] for row in self.report['buildings']),self.report['added_faces'])
        for row in self.report['buildings']:
            self.assertEqual(self.buildings[row['building_id']]['extras']['source_faces_preserved'],row['original_faces'])
            if row['kind']!='hospital':self.assertGreater(row['added_faces'],0)


if __name__=='__main__':unittest.main()
