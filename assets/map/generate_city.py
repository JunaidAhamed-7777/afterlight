#!/usr/bin/env python3
"""Original deterministic Afterlight city. Standard library only; no external assets."""
import json, math, random, hashlib
from pathlib import Path
OUT=Path(__file__).resolve().parent
rng=random.Random(250100)
# Twice the original linear extent, with infill streets at the original block scale.
X=[-880,-670,-460,-230,0,245,490,705,920]; Y=[-870,-660,-450,-225,0,215,430,665,900]
GRID=len(X); BLOCKS=GRID-1; ARTERIAL_ROWS={1,3,5,7}; ARTERIAL_COLUMNS={2,6}
nodes=[]; roads=[]; buildings=[]; parcels=[]; hospitals=[]
def node(id,x,y,kind='connector',signal=False):
    n=dict(id=id,position=[x,y,0],kind=kind,signalized=signal);nodes.append(n);return id
def road(id,a,b,width,kind='local',lanes=1):
    lookup={n['id']:n for n in nodes}
    r=dict(id=id,from_node=a,to_node=b,centerline=[lookup[a]['position'],lookup[b]['position']],width_m=width,sidewalk_width_m=3 if kind=='arterial' else 2,kind=kind,lanes_per_direction=lanes,lane_width_m=3.25,speed_kph=40 if kind=='arterial' else 25 if kind=='local' else 15,travel_permissions=['passenger','emergency'],two_way=True);roads.append(r);return r
for j,y in enumerate(Y):
 for i,x in enumerate(X):node(f'J{j}{i}',x,y,'primary_intersection',0<i<GRID-1 or 0<j<GRID-1)
for j in range(GRID):
 for i in range(BLOCKS):road(f'H{j}{i}',f'J{j}{i}',f'J{j}{i+1}',18 if j in ARTERIAL_ROWS else 10,'arterial' if j in ARTERIAL_ROWS else 'local',2 if j in ARTERIAL_ROWS else 1)
for i in range(GRID):
 for j in range(BLOCKS):road(f'V{i}{j}',f'J{j}{i}',f'J{j+1}{i}',18 if i in ARTERIAL_COLUMNS else 10,'arterial' if i in ARTERIAL_COLUMNS else 'local',2 if i in ARTERIAL_COLUMNS else 1)
# Roads retain canonical unsplit geometry; graph edges split them at attachment nodes.
attachments={r['id']:[] for r in roads}
parks={(1,2),(2,0),(5,1),(6,3),(1,6),(3,5),(5,6),(6,7)}
# Opposite diagonal quadrants, on dedicated driveways with independent arrival nodes.
hospital_blocks={(0,1):'HOSP_WEST',(7,6):'HOSP_EAST'}
for j in range(BLOCKS):
 for i in range(BLOCKS):
  x0,x1=X[i],X[i+1];y0,y1=Y[j],Y[j+1]
  if (i,j) in parks:
   parcels.append(dict(id=f'PARK_{i}{j}',kind='park',center=[(x0+x1)/2,(y0+y1)/2],size=[x1-x0-42,y1-y0-42],color=[0.32,0.61,0.39]));continue
  if (i,j) in hospital_blocks:
   hid=hospital_blocks[i,j];cx=(x0+x1)/2;cy=(y0+y1)/2
   parcels.append(dict(id=hid+'_PARCEL',kind='hospital',center=[cx,cy],size=[126,130],color=[0.58,0.66,0.65]))
   buildings.append(dict(id=hid+'_BUILDING',kind='hospital',center=[cx,cy+14],size=[76,60],height_m=26,color=[0.87,0.91,0.87],parcel_id=hid+'_PARCEL'))
   a=node(hid+'_ACCESS',cx,y0,'driveway_junction');b=node(hid+'_ARRIVAL',cx,cy-28,'hospital_destination');attachments[f'H{j}{i}'].append(a)
   road(hid+'_DRIVEWAY',a,b,7,'driveway');hospitals.append(dict(id=hid,name='Westhaven Medical' if i==0 else 'Eastbank General',building_id=hid+'_BUILDING',destination_node=b,driveway_road_id=hid+'_DRIVEWAY',driveway_anchor=[cx,cy-28,0]));continue
  # Small service U streets, subordinate to the 25 main intersections.
  if (i+j)%2==0:
   a=node(f'L{i}{j}A',x0+.26*(x1-x0),y0);b=node(f'L{i}{j}B',x0+.74*(x1-x0),y0)
   c=node(f'L{i}{j}C',x0+.26*(x1-x0),y0+.48*(y1-y0));d=node(f'L{i}{j}D',x0+.74*(x1-x0),y0+.48*(y1-y0))
   attachments[f'H{j}{i}'] += [a,b]
   for k,u,v in [(0,a,c),(1,c,d),(2,d,b)]:road(f'LOCAL_{i}{j}_{k}',u,v,8,'local')
# Rectangular geometry tests (roads axis aligned by design).
def rect(center,size):return(center[0]-size[0]/2,center[1]-size[1]/2,center[0]+size[0]/2,center[1]+size[1]/2)
def overlap(a,b,margin=0):return a[0]<b[2]+margin and a[2]>b[0]-margin and a[1]<b[3]+margin and a[3]>b[1]-margin
def roadrect(r,pad=0):
 a,b=r['centerline'];h=r['width_m']/2+pad
 return(min(a[0],b[0])-h,min(a[1],b[1])-h,max(a[0],b[0])+h,max(a[1],b[1])+h)
colors=[[0.74,0.53,0.40],[0.76,0.69,0.49],[0.52,0.65,0.68],[0.65,0.57,0.72]]
for j in range(BLOCKS):
 for i in range(BLOCKS):
  if (i,j) in parks or (i,j) in hospital_blocks:continue
  for x in range(X[i]+36,X[i+1]-20,40):
   for y in range(Y[j]+36,Y[j+1]-20,40):
    size=[rng.randint(22,29),rng.randint(22,29)];rr=rect([x,y],[size[0]+6,size[1]+6])
    if any(overlap(rr,roadrect(r,3)) for r in roads):continue
    bid=f'B{len(buildings):04d}';pid=bid+'_PARCEL';height=rng.randint(15,48) if i in [2,3,4,5] else rng.randint(8,25)
    parcels.append(dict(id=pid,kind='building',center=[x,y],size=[size[0]+6,size[1]+6],color=[0.55,0.62,0.53]))
    buildings.append(dict(id=bid,kind='residential' if i in [0,1,6,7] else 'mixed_use',center=[x,y],size=size,height_m=height,color=colors[(i+j)%4],parcel_id=pid))
lookup={n['id']:n for n in nodes};edges=[]
for r in roads:
 a,b=r['centerline'];dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
 chain=[r['from_node']]+attachments.get(r['id'],[])+[r['to_node']]
 chain.sort(key=lambda k:(lookup[k]['position'][0]-a[0])*dx+(lookup[k]['position'][1]-a[1])*dy)
 for k,(u,v) in enumerate(zip(chain,chain[1:])):
  for suffix,start,end in [('F',u,v),('R',v,u)]:
   p,q=lookup[start]['position'],lookup[end]['position'];L=math.dist(p,q); stop=min(12,L/4)
   edges.append(dict(id=f'{r["id"]}_{k}_{suffix}',road_id=r['id'],from_node=start,to_node=end,centerline=[p,q],length_m=round(L,6),lanes=r['lanes_per_direction'],lane_width_m=3.25,speed_kph=r['speed_kph'],permissions=r['travel_permissions'],stop_line=dict(distance_before_node_m=stop,signal_id=end if lookup[end]['signalized'] else None)))
# Every legal transition except U turns. Lane-level turn curves remain importer responsibility.
connections=[]
for e in edges:
 for f in edges:
  if e['to_node']==f['from_node'] and e['from_node']!=f['to_node']:
   connections.append(dict(from_edge=e['id'],to_edge=f['id'],via_node=e['to_node']))
pickups=[]
for r in roads:
 if r['kind']=='driveway':continue
 a,b=r['centerline'];dx=b[0]-a[0];dy=b[1]-a[1];L=math.hypot(dx,dy);nx=-dy/L;ny=dx/L
 for fraction in [.38,.62,.48,.82,.18]:
  for side in [1,-1]:
   center=[a[0]+dx*fraction,a[1]+dy*fraction];offset=r['width_m']/2+1.5;p=[round(center[0]+side*nx*offset,3),round(center[1]+side*ny*offset,3),0]
   if any(math.dist(p[:2],n['position'][:2])<27 for n in nodes):continue
   if any(overlap(rect(p,[2,2]),rect(z['center'],z['size'])) for z in buildings):continue
   if any(math.dist(p[:2],z['position'][:2])<12 for z in pickups):continue
   forward=side==-1 # right-hand traffic: canonical forward uses right curb
   candidates=[e for e in edges if e['road_id']==r['id'] and e['id'].endswith('_F' if forward else '_R')]
   edge=next((e for e in candidates if min(e['centerline'][0][0],e['centerline'][1][0])-.001<=center[0]<=max(e['centerline'][0][0],e['centerline'][1][0])+.001 and min(e['centerline'][0][1],e['centerline'][1][1])-.001<=center[1]<=max(e['centerline'][0][1],e['centerline'][1][1])+.001),None)
   if edge:pickups.append(dict(id=f'P{len(pickups)+1:03}',position=p,road_id=r['id'],edge_id=edge['id'],curb_side='left' if side==1 else 'right',road_fraction=fraction,curb_offset_m=1.5))
# Evenly distribute exact 100 across all available corridors rather than taking first roads only.
assert len(pickups)>=100
pickups=[pickups[round(k*(len(pickups)-1)/99)] for k in range(100)]
for k,p in enumerate(pickups):p['id']=f'P{k+1:03}'
manifest=dict(schema='afterlight.city.v1',seed=250100,coordinate_system=dict(units='meters',ground_plane='XY',up='Z',origin='city center; local Cartesian, no georeference',traffic_side='right'),bounds=dict(min=[-1000,-990,0],max=[1040,1020,70]),expansion=dict(linear_factor=2,area_factor=4,original_bounds=dict(min=[-500,-495,0],max=[520,510,70]),grid_shape=[GRID,GRID],block_count=BLOCKS*BLOCKS),primary_intersection_count=GRID*GRID,nodes=nodes,roads=roads,edges=edges,connections=connections,buildings=buildings,parcels=parcels,hospitals=hospitals,pickups=pickups,neighborhoods=[dict(id='WESTHAVEN',label='Westhaven',center=[-650,-400]),dict(id='CIVIC',label='Civic Quarter',center=[-200,350]),dict(id='MARKET',label='Market Gardens',center=[300,-350]),dict(id='EASTBANK',label='Eastbank',center=[700,400])],render_budget=dict(static_triangles_target=600000,glb_bytes_target=20000000,building_style='original low-poly cuboids; shared palette; no textures required'),simulation=dict(status='canonical expanded topology; SUMO scheduler and independent-world replay implemented; qualification is recorded separately',ghost_baseline='separate nonphysical simulation overlay; never inserted into road graph or traffic vehicle population'))
(OUT/'city_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Wrote',OUT/'city_manifest.json', {k:len(manifest[k]) for k in ['nodes','roads','edges','buildings','parcels','pickups','hospitals']})
