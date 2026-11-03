#!/usr/bin/env python3
"""Independent graph/spatial validation, not a traffic-simulator test."""
import json,math,hashlib,collections
from pathlib import Path
P=Path(__file__).resolve().parent
raw=(P/'city_manifest.json').read_bytes();m=json.loads(raw);checks=[]
def check(name,condition,detail=''):
 checks.append(dict(name=name,passed=bool(condition),detail=detail));return condition
def rect(o):
 x,y=o['center'];w,h=o['size'];return[x-w/2,y-h/2,x+w/2,y+h/2]
def overlaps(a,b):return a[0]<b[2]-1e-6 and a[2]>b[0]+1e-6 and a[1]<b[3]-1e-6 and a[3]>b[1]+1e-6
def rr(r):
 a,b=r['centerline'];h=r['width_m']/2;return[min(a[0],b[0])-h,min(a[1],b[1])-h,max(a[0],b[0])+h,max(a[1],b[1])+h]
def point_segment(p,a,b):
 dx=b[0]-a[0];dy=b[1]-a[1];t=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/(dx*dx+dy*dy);q=[a[0]+max(0,min(1,t))*dx,a[1]+max(0,min(1,t))*dy];return math.dist(p[:2],q),t
nodes={n['id']:n for n in m['nodes']};roads={r['id']:r for r in m['roads']};edges={e['id']:e for e in m['edges']}
for key in ['nodes','roads','edges','buildings','parcels','hospitals','pickups']:
 check(key+'_unique_ids',len({x['id'] for x in m[key]})==len(m[key]))
check('81_primary_intersections',sum(n['kind']=='primary_intersection' for n in nodes.values())==81==m['primary_intersection_count'])
original=m['expansion']['original_bounds'];lo=m['bounds']['min'];hi=m['bounds']['max']
check('four_times_original_map_area',(hi[0]-lo[0])*(hi[1]-lo[1])==4*(original['max'][0]-original['min'][0])*(original['max'][1]-original['min'][1]))
centres=[next(b['center'] for b in m['buildings'] if b['id']==h['building_id']) for h in m['hospitals']]
check('hospitals_in_diagonal_quadrants',len(centres)==2 and centres[0][0]*centres[1][0]<0 and centres[0][1]*centres[1][1]<0)
check('100_pickups',len(m['pickups'])==100);check('2_hospitals',len(m['hospitals'])==2)
check('edge_references',all(e['from_node'] in nodes and e['to_node'] in nodes and e['road_id'] in roads for e in edges.values()))
check('road_endpoints_match_nodes',all(r['centerline']==[nodes[r['from_node']]['position'],nodes[r['to_node']]['position']] for r in roads.values()))
check('edge_geometry_and_length',all(e['centerline']==[nodes[e['from_node']]['position'],nodes[e['to_node']]['position']] and abs(math.dist(*e['centerline'])-e['length_m'])<1e-5 and e['length_m']>0 for e in edges.values()))
check('bidirectional_permissions',all(any(f['from_node']==e['to_node'] and f['to_node']==e['from_node'] and f['road_id']==e['road_id'] and f['permissions']==e['permissions'] for f in edges.values()) for e in edges.values()))
check('lane_width_fits_road',all(2*r['lanes_per_direction']*r['lane_width_m']<=r['width_m'] for r in roads.values()))
check('stoplines_and_signals',all(0<e['stop_line']['distance_before_node_m']<e['length_m'] and e['stop_line']['signal_id']==(e['to_node'] if nodes[e['to_node']]['signalized'] else None) for e in edges.values()))
adj=collections.defaultdict(list)
for e in edges.values():adj[e['from_node']].append(e['to_node'])
def reachable(start,adj):
 seen={start};todo=[start]
 while todo:
  for v in adj[todo.pop()]:
   if v not in seen:seen.add(v);todo.append(v)
 return seen
check('strongly_connected_graph',all(len(reachable(n,adj))==len(nodes) for n in nodes))
check('legal_turn_references',all(c['from_edge'] in edges and c['to_edge'] in edges and edges[c['from_edge']]['to_node']==c['via_node']==edges[c['to_edge']]['from_node'] and edges[c['from_edge']]['from_node']!=edges[c['to_edge']]['to_node'] for c in m['connections']))
turnadj=collections.defaultdict(list)
for c in m['connections']:turnadj[c['from_edge']].append(c['to_edge'])
route_count=0;route_failures=[]
for p in m['pickups']:
 allowed_edges=reachable(p['edge_id'],turnadj)
 for h in m['hospitals']:
  ok=any(edges[e]['to_node']==h['destination_node'] for e in allowed_edges)
  route_count+=ok
  if not ok:route_failures.append([p['id'],h['id']])
check('200_pickup_to_hospital_routes',route_count==200,dict(passed=route_count,total=200,failures=route_failures))
check('hospital_driveway_anchors',all(h['destination_node'] in nodes and h['driveway_road_id'] in roads and h['driveway_anchor']==nodes[h['destination_node']]['position'] and roads[h['driveway_road_id']]['to_node']==h['destination_node'] for h in m['hospitals']))
curb_failures=[]
for p in m['pickups']:
 r=roads[p['road_id']];e=edges[p['edge_id']];a,b=r['centerline'];dist,t=point_segment(p['position'],a,b);edist,et=point_segment(p['position'],*e['centerline'])
 cross=(b[0]-a[0])*(p['position'][1]-a[1])-(b[1]-a[1])*(p['position'][0]-a[0])
 ok=abs(dist-r['width_m']/2-p['curb_offset_m'])<.002 and 0<t<1 and -.00001<=et<=1.00001 and e['road_id']==r['id'] and ((cross>0)==(p['curb_side']=='left')) and p['edge_id'].endswith('_R' if cross>0 else '_F')
 if not ok:curb_failures.append(p['id'])
check('pickup_correct_curb_and_directed_edge',not curb_failures,curb_failures)
minimum=min(math.dist(p['position'][:2],n['position'][:2]) for p in m['pickups'] for n in nodes.values())
check('pickups_outside_intersections',minimum>=27,dict(minimum_node_distance_m=minimum,required_minimum_m=27))
check('pickups_outside_all_buildings',all(not overlaps([p['position'][0]-1,p['position'][1]-1,p['position'][0]+1,p['position'][1]+1],rect(b)) for p in m['pickups'] for b in m['buildings']))
check('pickups_outside_all_road_surfaces',all(not(rr(r)[0]<p['position'][0]<rr(r)[2] and rr(r)[1]<p['position'][1]<rr(r)[3]) for p in m['pickups'] for r in roads.values()))
check('buildings_do_not_overlap',all(not overlaps(rect(a),rect(b)) for i,a in enumerate(m['buildings']) for b in m['buildings'][i+1:]))
check('parcels_do_not_overlap',all(not overlaps(rect(a),rect(b)) for i,a in enumerate(m['parcels']) for b in m['parcels'][i+1:]))
check('buildings_clear_road_surfaces',all(not overlaps(rect(b),rr(r)) for b in m['buildings'] for r in roads.values()))
parcels={p['id']:p for p in m['parcels']}
check('buildings_inside_assigned_parcels',all(all([rect(parcels[b['parcel_id']])[0]<=rect(b)[0],rect(parcels[b['parcel_id']])[1]<=rect(b)[1],rect(parcels[b['parcel_id']])[2]>=rect(b)[2],rect(parcels[b['parcel_id']])[3]>=rect(b)[3]]) for b in m['buildings']))
lo=m['bounds']['min'];hi=m['bounds']['max'];allrect=[rect(o) for k in ['buildings','parcels'] for o in m[k]]+[rr(r) for r in roads.values()]
check('all_geometry_within_declared_bounds',all(lo[0]<=r[0] and lo[1]<=r[1] and hi[0]>=r[2] and hi[1]>=r[3] for r in allrect) and all(b['height_m']<=hi[2] for b in m['buildings']) and all(all(lo[i]<=p['position'][i]<=hi[i] for i in range(3)) for p in m['pickups']))
# Every crossing of distinct road surfaces must have graph attachment, avoiding phantom crossings.
cross_fail=[]
for i,a in enumerate(m['roads']):
 for b in m['roads'][i+1:]:
  ap,aq=a['centerline'];bp,bq=b['centerline'];av=ap[0]==aq[0];bv=bp[0]==bq[0]
  if av==bv:continue
  v,h=(a,b) if av else (b,a);vp,vq=v['centerline'];hp,hq=h['centerline'];x=vp[0];y=hp[1]
  if min(hp[0],hq[0])<=x<=max(hp[0],hq[0]) and min(vp[1],vq[1])<=y<=max(vp[1],vq[1]):
   common={e['from_node'] for e in edges.values() if e['road_id']==a['id']} & {e['from_node'] for e in edges.values() if e['road_id']==b['id']}
   if not any(nodes[n]['position'][:2]==[x,y] for n in common):cross_fail.append([a['id'],b['id']])
check('all_centerline_crossings_have_graph_nodes',not cross_fail,cross_fail)
report=dict(manifest_sha256=hashlib.sha256(raw).hexdigest(),status='PASS' if all(c['passed'] for c in checks) else 'FAIL',checks=checks,counts={k:len(m[k]) for k in ['nodes','roads','edges','connections','buildings','parcels','pickups','hospitals']},primary_intersections=m['primary_intersection_count'],additional_nodes=len(nodes)-m['primary_intersection_count'],limitations=['This independent static report does not run SUMO; executed conversion/traffic evidence is recorded separately.','Signal metadata is not signal phases or a deployed controller.','Turn connections are topological, not lane-level swept paths.','Static GLB budget is a target; actual triangles/bytes must be checked after Blender export.','Ghost baseline is a separate nonphysical overlay, not present in this graph.'])
(P/'validation_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps(report,indent=2));raise SystemExit(0 if report['status']=='PASS' else 1)
