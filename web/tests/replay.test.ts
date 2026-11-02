import test from 'node:test';
import assert from 'node:assert/strict';
import { frameAt, validateReplay, vehiclePose } from '../src/replay.ts';
import type { Replay, Vehicle, Frame } from '../src/types.ts';
const vehicle: Vehicle = {id:'ambulance',type:'ambulance',x:100,y:200,z:0,angle_deg:0,speed_mps:10,length_m:6};
const frame=(t:number):Frame=>({t,vehicles:[{...vehicle}],signals:[],queue_count:0});
function recording():Replay {return {schema:'afterlight.replay.v1',mode:'recorded',scenario:{id:'test-fixture-only',network_kind:'fixture',seed:1,pickup_id:'fixture_start',hospital_id:'fixture_end',dispatch_s:0},coordinates:{source:'canonical XY meters',position_reference:'front_bumper',render:'[x,z,-y]'},provenance:{source_commit:'unit-fixture',network_sha256:'a'.repeat(64),demand_sha256:'b'.repeat(64),sumo_version:'not-a-simulation'},duration_s:1,step_s:1,worlds:{afterlight:{policy:'fixed',status:'completed',metrics:{},events:[],frames:[frame(0),frame(1)]},baseline:{policy:'ordinary',status:'completed',metrics:{},events:[],frames:[frame(0),frame(1)]}}};}
test('north heading converts front bumper to model center without changing absolute scale',()=>{assert.deepEqual(vehiclePose(vehicle),[100,0,-197,-0]);});
test('east heading rotates model forward -Z to +X and offsets center',()=>{const pose=vehiclePose({...vehicle,angle_deg:90});assert.equal(pose[0],97);assert.equal(pose[2],-200);assert.equal(pose[3],-Math.PI/2);});
test('frame lookup uses one absolute clock and never extrapolates before beginning',()=>{const frames=[frame(2),frame(4),frame(8)];assert.equal(frameAt(frames,1),null);assert.equal(frameAt(frames,5)?.t,4);assert.equal(frameAt(frames,8)?.t,8);assert.equal(frameAt(frames,9),null);});
test('valid fixture may be inspected but remains explicitly fixture',()=>{assert.equal(validateReplay(recording()).scenario.network_kind,'fixture');});
test('unknown map provenance is rejected rather than overlaid on the city',()=>{const r=recording();delete (r.scenario as Partial<Replay['scenario']>).network_kind;assert.throws(()=>validateReplay(r),/contract/);});
test('duplicate vehicle IDs fail closed',()=>{const r=recording();r.worlds.afterlight.frames[0].vehicles.push({...vehicle});assert.throws(()=>validateReplay(r),/invalid vehicle pose/);});
test('out-of-order samples fail closed',()=>{const r=recording();r.worlds.afterlight.frames[1].t=0;assert.throws(()=>validateReplay(r),/timestamps/);});
test('worlds must have identical sampled absolute timestamps',()=>{const r=recording();r.worlds.baseline.frames[1].t=.5;assert.throws(()=>validateReplay(r),/absolute time/);});
test('ghost pose is baseline data and does not mutate active world',()=>{const r=recording();r.worlds.baseline.frames[0].vehicles[0].x=70;const before=JSON.stringify(r.worlds.afterlight);assert.equal(vehiclePose(frameAt(r.worlds.baseline.frames,0)!.vehicles[0])[0],70);assert.equal(JSON.stringify(r.worlds.afterlight),before);});
test('non-finite vehicle position rejected',()=>{const r=recording();r.worlds.baseline.frames[0].vehicles[0].x=NaN;assert.throws(()=>validateReplay(r),/invalid vehicle pose/);});
