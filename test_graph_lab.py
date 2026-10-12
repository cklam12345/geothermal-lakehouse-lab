import copy
import unittest
from graph_lab import make_graph, validate


class OntologyContractTests(unittest.TestCase):
    def setUp(self):
        self.graph = make_graph()

    def test_fixture_and_missing_context(self):
        validate(self.graph)
        observations = [n for n in self.graph['nodes'] if n['kind'] == 'Observation']
        self.assertEqual(len(observations), 11)
        self.assertTrue(all(n['observed_at'] == 'unknown' for n in observations))
        self.assertFalse(any(n['title'].startswith('W004:') and 'degC' in n['title'] for n in observations))
        rejected = [n for n in observations if n['quality'] == 'rejected']
        self.assertEqual([n['value'] for n in rejected], [-5.0])

    def test_wrong_relationship_type_is_rejected(self):
        graph = copy.deepcopy(self.graph)
        edge = next(e for e in graph['edges'] if e['relation'] == 'ABOUT')
        edge['target'] = 'unit:degC'
        with self.assertRaises(AssertionError):
            validate(graph)

    def test_observation_without_provenance_is_rejected(self):
        edge = next(e for e in self.graph['edges'] if e['relation'] == 'SOURCED_FROM')
        self.graph['edges'].remove(edge)
        with self.assertRaises(AssertionError):
            validate(self.graph)

    def test_repeatable_source_identity(self):
        self.assertEqual(make_graph(), make_graph())


if __name__ == '__main__':
    unittest.main()
