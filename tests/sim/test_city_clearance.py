"""Controller-profile evidence checks; no SUMO execution or invented results."""
import unittest
from policies.scheduler import Scheduler, Timing, timing_for_network
from sim.audit import audit_world_signals


class CityClearanceTests(unittest.TestCase):
    def world(self, timing):
        scheduler=Scheduler('J',('GGrr','rrGG'),timing=timing)
        frames=[]
        for tick in range(141):
            now=tick*.5
            state=scheduler.advance(now)
            frames.append({'t':now,'signals':[{'id':'J','state':state}]})
        return {'world_id':'ordinary','policy':'ordinary','decision':{'request_plan':{}},
                'metrics':{'simulation_step_s':.5,'controller_timing':dict(vars(timing))},
                'events':scheduler.events,'frames':frames}

    def test_city_holds_full_three_second_clearance_and_fixture_stays_one(self):
        self.assertEqual(timing_for_network('fixture').all_red_s,1)
        timing=timing_for_network('city');self.assertEqual(timing.all_red_s,3)
        scheduler=Scheduler('J',('GGrr','rrGG'),timing=timing)
        self.assertEqual(scheduler.advance(25),'yyrr')
        self.assertEqual(scheduler.advance(28),'rrrr')
        self.assertEqual(scheduler.advance(30.5),'rrrr')
        self.assertEqual(scheduler.advance(31),'rrGG')
        audit_world_signals(self.world(timing),{'signals':{'J':{'greens':['GGrr','rrGG']}}},60)

    def test_one_second_capture_cannot_be_relabelled_three_seconds(self):
        world=self.world(timing_for_network('fixture'))
        world['metrics']['controller_timing']=dict(vars(timing_for_network('city')))
        with self.assertRaisesRegex(ValueError,'too-short transition'):
            audit_world_signals(world,{'signals':{'J':{'greens':['GGrr','rrGG']}}},60)

    def test_historical_profile_remains_auditable_and_invalid_types_fail(self):
        world=self.world(Timing());del world['metrics']['controller_timing']
        audit_world_signals(world,{'signals':{'J':{'greens':['GGrr','rrGG']}}},60)
        with self.assertRaises(ValueError):Timing(all_red_s=True)
        with self.assertRaises(ValueError):Timing(all_red_s=10**1000)
        with self.assertRaises(ValueError):timing_for_network('unknown')


if __name__=='__main__':unittest.main()
