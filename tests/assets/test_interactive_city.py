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
        cls.root=cls.nodes[cls.gltf['scenes'][cls.gltf.get('scene',0)]['nodes'][0]]
        cls.buildings={n['extras']['building_id']:n for n in cls.nodes if 'building_id' in n.get('extras',{})}

    def world_positions(self,node):
        transform=multiply(matrix(self.root),matrix(node))
        return [point(transform,p) for primitive in self.gltf['meshes'][node['mesh']]['primitives']
                for p in accessor(self.gltf,self.binary,primitive['attributes']['POSITION'])]

    def test_original_vehicle_and_original_city_bytes_preserved(self):
        for relative,expected in ORIGINAL_HASHES.items():
            with self.subTest(path=relative):
                self.assertEqual(hashlib.sha256((ASSETS/relative).read_bytes()).hexdigest(),expected)

    def test_deployed_asset_budget_and_exact_source_binding(self):
        self.assertLessEqual(len(self.raw),MAX_BYTES)
        self.assertEqual(self.report['asset_bytes'],len(self.raw))
        self.assertEqual(self.report['asset_sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(self.report['provenance']['canonical_map_sha256'],hashlib.sha256((ASSETS/'map/city_manifest.json').read_bytes()).hexdigest())
        self.assertEqual(self.report['provenance']['generator_sha256'],hashlib.sha256((ASSETS/'src/generate_city_v4.py').read_bytes()).hexdigest())
        self.assertEqual(self.report['enhancement_revision'],'v4-expanded-architectural-miniature')
        self.assertLessEqual(sum(p.stat().st_size for p in (ASSETS/'exports').glob('*') if p.is_file()),50_000_000)

    def test_embedded_real_geometry_without_external_texture_dependencies(self):
        self.assertEqual(self.gltf['asset']['version'],'2.0')
        self.assertEqual(len(self.gltf['buffers']),1)
        self.assertNotIn('uri',self.gltf['buffers'][0])
        self.assertFalse(self.gltf.get('images',[]))
        self.assertFalse(self.gltf.get('animations',[]))
        self.assertFalse(self.gltf.get('skins',[]))
        self.assertEqual(len(self.nodes),len(self.graph['buildings'])+2)
        for index in range(len(self.gltf['accessors'])):
            with self.subTest(accessor=index):accessor(self.gltf,self.binary,index)

    def test_complete_unique_building_ownership_and_preserved_root(self):
        expected={b['id'] for b in self.graph['buildings']}
        listed=[n['extras']['building_id'] for n in self.nodes if 'building_id' in n.get('extras',{})]
        self.assertEqual(set(listed),expected)
        self.assertEqual(len(listed),len(expected))
        self.assertEqual(self.report['building_count'],len(expected))
        self.assertEqual(self.root['name'],'AFTERLIGHT_CITY')
        self.assertEqual(self.root.get('translation'),[10,-3,-7.5])
        self.assertEqual(self.root['extras']['canonical_map_sha256'],self.report['provenance']['canonical_map_sha256'])
        mesh_nodes=[n for n in self.nodes if 'mesh' in n]
        self.assertEqual(len(set(n['mesh'] for n in mesh_nodes)),len(mesh_nodes))
        for node in mesh_nodes:
            self.assertEqual(matrix(node),matrix({}),'Children must not double-transform root-local geometry')
            if 'building_id' in node.get('extras',{}):
                self.assertEqual(node['name'],'AL_BUILDING_'+node['extras']['building_id'])
                self.assertIs(node['extras']['occluder'],True)
            else:
                self.assertEqual(node['name'],'AL_GROUND')
                self.assertIs(node['extras']['occluder'],False)

    def test_real_volumes_match_every_canonical_footprint_and_reported_bounds(self):
        reports={b['building_id']:b for b in self.report['buildings']}
        for building in self.graph['buildings']:
            with self.subTest(building=building['id']):
                points=self.world_positions(self.buildings[building['id']])
                low=[min(p[i] for p in points) for i in range(3)]
                high=[max(p[i] for p in points) for i in range(3)]
                x,y=building['center'];w,d=building['size']
                self.assertLessEqual(low[0],x-w/2+.005)
                self.assertGreaterEqual(high[0],x+w/2-.005)
                self.assertLessEqual(low[2],-y-d/2+.005)
                self.assertGreaterEqual(high[2],-y+d/2-.005)
                self.assertGreaterEqual(high[1]-low[1],building['height_m']-.005)
                for measured,expected in zip([*low,*high],sum(reports[building['id']]['world_bounds_render_m'],[])):
                    self.assertAlmostEqual(measured,expected,delta=.005)

    def test_canonical_road_surface_is_physically_present_at_018_metres(self):
        ground=next(n for n in self.nodes if n.get('name')=='AL_GROUND')
        points=self.world_positions(ground)
        surface={(round(x,2),round(-z,2)) for x,y,z in points if abs(y-.18)<.001}
        for road in self.graph['roads']:
            for a,b in zip(road['centerline'],road['centerline'][1:]):
                dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
                nx,ny=-dy/length,dx/length
                for endpoint,direction in ((a,-1),(b,1)):
                    for side in (-1,1):
                        x=endpoint[0]+direction*.05*dx/length+side*nx*road['width_m']/2
                        y=endpoint[1]+direction*.05*dy/length+side*ny*road['width_m']/2
                        self.assertIn((round(x,2),round(y,2)),surface,road['id'])

    def test_expansion_adds_city_geometry_and_diagonal_hospital_landmarks(self):
        self.assertEqual(self.graph['expansion']['area_factor'],4)
        self.assertEqual(self.graph['primary_intersection_count'],81)
        self.assertGreaterEqual(len(self.buildings),800)
        landmarks=[b for b in self.graph['buildings'] if b['kind']=='hospital']
        self.assertEqual(len(landmarks),2)
        a,b=[item['center'] for item in landmarks]
        self.assertLess(a[0]*b[0],0)
        self.assertLess(a[1]*b[1],0)
        for landmark in landmarks:
            node=self.buildings[landmark['id']]
            primitives=self.gltf['meshes'][node['mesh']]['primitives']
            count=sum(len(accessor(self.gltf,self.binary,p['indices']))//3 for p in primitives)
            self.assertGreater(count,250,'Hospitals must be actual detailed landmark volumes')
        self.assertGreater(self.report['scenery']['trees'],300)
        self.assertGreater(self.report['scenery']['streetlights'],200)

    def test_hospital_plazas_leave_real_depth_separation_from_driveways(self):
        ground=next(n for n in self.nodes if n.get('name')=='AL_GROUND')
        transform=multiply(matrix(self.root),matrix(ground))
        plaza=set()
        for primitive in self.gltf['meshes'][ground['mesh']]['primitives']:
            if self.gltf['materials'][primitive['material']]['name']!='plaza':continue
            for p in accessor(self.gltf,self.binary,primitive['attributes']['POSITION']):
                x,y,z=point(transform,p)
                plaza.add((round(x,2),round(-z,2),round(y,2)))
        for parcel in self.graph['parcels']:
            if parcel['kind']!='hospital':continue
            x,y=parcel['center'];w,d=parcel['size']
            for sx in (-1,1):
                for sy in (-1,1):
                    corner=(round(x+sx*w/2,2),round(y+sy*d/2,2))
                    self.assertIn((*corner,.14),plaza)
                    self.assertNotIn((*corner,.18),plaza,'Visual plaza must not be coplanar with canonical driveway')

    def test_exact_triangle_inventory_finite_surfaces_and_valid_opaque_materials(self):
        triangles=0
        for mesh in self.gltf['meshes']:
            for primitive in mesh['primitives']:
                positions=accessor(self.gltf,self.binary,primitive['attributes']['POSITION'])
                indices=[v[0] for v in accessor(self.gltf,self.binary,primitive['indices'])]
                self.assertEqual(len(indices)%3,0)
                self.assertTrue(all(0<=i<len(positions) for i in indices))
                triangles+=len(indices)//3
                self.assertGreater(sum(area_squared(*(positions[indices[i+j]] for j in range(3)))>1e-12 for i in range(0,len(indices),3)),0)
                self.assertTrue(0<=primitive['material']<len(self.gltf['materials']))
        self.assertEqual(triangles,self.report['triangles'])
        self.assertLess(triangles,300_000)
        for material in self.gltf['materials']:
            self.assertEqual(material.get('alphaMode','OPAQUE'),'OPAQUE')
            self.assertEqual(material.get('pbrMetallicRoughness',{}).get('baseColorFactor',[1,1,1,1])[3],1)


if __name__=='__main__':unittest.main()
