"""Pure latent-RNG identity regressions, not real demand generation or outcomes."""
from copy import deepcopy
import unittest
from evaluation.study_manifest import seed_assignments, validate_pilot_seed_exclusion
from evaluation.protocol import validate_episode_inventory, assert_episode_coverage


def protocol_fixture():
    cases=[{'episode_id':split,'demand_group_id':split,'split':split,'regime':regime,'seed':seed,
            'demand_sha256':'bytes-'+split,'network_sha256':'network','dispatch_s':60}
           for split,regime,seed in [('train','moderate',2001),('validation','moderate',2002),('test','heavy',2003)]]
    return {'episode_inventory':cases,'group_assignments':{case['demand_group_id']:case['split'] for case in cases},
            'heldout_regimes':['heavy'],'seed_assignments':seed_assignments(cases)}


class SeedIsolationTests(unittest.TestCase):
    def test_same_seed_cross_split_rejected_even_with_different_regime(self):
        for regime in ('moderate','heavy'):
            cases=[{'seed':17,'split':'train','regime':'moderate'},{'seed':17,'split':'test','regime':regime}]
            with self.subTest(regime=regime),self.assertRaisesRegex(ValueError,'one split and regime'):
                seed_assignments(cases)

    def test_same_seed_cross_regime_within_test_is_not_independent_group(self):
        with self.assertRaises(ValueError):seed_assignments([
            {'seed':17,'split':'test','regime':'sparse'},{'seed':17,'split':'test','regime':'heavy'}])

    def test_same_pair_dispatch_route_variants_share_stream(self):
        cases=[{'seed':17,'split':'train','regime':'moderate','dispatch_s':20,'route':'a'},
               {'seed':17,'split':'train','regime':'moderate','dispatch_s':40,'route':'b'}]
        self.assertEqual(seed_assignments(cases),{'17':{'split':'train','regime':'moderate'}})

    def test_pilot_seed_exclusion_ignores_changed_regime_and_content_hash(self):
        evidence={'schema':'afterlight.pilot-evidence.v2','seeds':[7,8]}
        with self.assertRaisesRegex(ValueError,'pilot RNG seed'):
            validate_pilot_seed_exclusion(evidence,[{'seed':7,'regime':'other','demand_group_id':'different'}])
        validate_pilot_seed_exclusion(evidence,[{'seed':9}])

    def test_legacy_missing_or_malformed_pilot_seed_inventory_rejected(self):
        for evidence in ({'schema':'afterlight.pilot-evidence.v1'},
                         {'schema':'afterlight.pilot-evidence.v2'},
                         {'schema':'afterlight.pilot-evidence.v2','seeds':[]},
                         {'schema':'afterlight.pilot-evidence.v2','seeds':[8,7]},
                         {'schema':'afterlight.pilot-evidence.v2','seeds':[7,7]},
                         {'schema':'afterlight.pilot-evidence.v2','seeds':[True]}):
            with self.subTest(evidence=evidence),self.assertRaises(ValueError):
                validate_pilot_seed_exclusion(evidence,[{'seed':9}])

    def test_new_protocol_seed_assignments_exact_inventory(self):
        protocol=protocol_fixture()
        self.assertEqual(len(validate_episode_inventory(protocol)),3)
        protocol['seed_assignments']['2003']['regime']='moderate'
        with self.assertRaisesRegex(ValueError,'seed assignments'):validate_episode_inventory(protocol)

    def test_rehashed_cross_regime_seed_cannot_evade_content_group_check(self):
        protocol=protocol_fixture()
        protocol['episode_inventory'][2]['seed']=2001
        protocol['seed_assignments'].pop('2003')
        with self.assertRaisesRegex(ValueError,'RNG seed crosses'):validate_episode_inventory(protocol)

    def test_seed_bound_protocol_requires_complete_seed_metadata(self):
        protocol=protocol_fixture();protocol['episode_inventory'][0].pop('seed')
        with self.assertRaisesRegex(ValueError,'explicit valid seed'):validate_episode_inventory(protocol)

    def test_candidate_seed_must_match_frozen_inventory(self):
        protocol=protocol_fixture();row=deepcopy(protocol['episode_inventory'][2]);row['seed']=999
        with self.assertRaisesRegex(ValueError,'RNG seed differs'):assert_episode_coverage([row],protocol,'test')

    def test_software_qualification_seed_is_reserved_for_every_split(self):
        for split in ('train','validation','test'):
            with self.subTest(split=split),self.assertRaisesRegex(ValueError,'qualification'):
                seed_assignments([{'seed':7,'split':split,'regime':'moderate'}])

    def test_protocol_cannot_relabel_qualification_seed_untouched(self):
        protocol=protocol_fixture()
        protocol['episode_inventory'][0]['seed']=7
        protocol['seed_assignments'].pop('2001')
        protocol['seed_assignments']['7']={'split':'train','regime':'moderate'}
        with self.assertRaisesRegex(ValueError,'qualification'):validate_episode_inventory(protocol)

    def test_protocol_declared_exploration_rejected_across_splits(self):
        for index in range(3):
            protocol=protocol_fixture()
            protocol['declared_exploration_seeds']=[protocol['episode_inventory'][index]['seed']]
            with self.subTest(index=index),self.assertRaisesRegex(ValueError,'operator-declared'):
                validate_episode_inventory(protocol)

    def test_explicit_empty_declaration_still_requires_seed_inventory(self):
        protocol=protocol_fixture();protocol['declared_exploration_seeds']=[]
        validate_episode_inventory(protocol)
        protocol.pop('seed_assignments')
        for item in protocol['episode_inventory']:item.pop('seed')
        with self.assertRaisesRegex(ValueError,'explicit valid seed'):validate_episode_inventory(protocol)
