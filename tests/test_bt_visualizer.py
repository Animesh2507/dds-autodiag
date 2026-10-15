import unittest
from autodiag.bt_visualizer import run_trace, simulate, TREE
class BTVisualizerTests(unittest.TestCase):
    def test_tree_structure(self):
        self.assertEqual([c['id'] for c in TREE['children']], ['collect','qos','report'])
    def test_simulation_events(self):
        self.assertEqual(len(simulate()), 9)
        self.assertEqual(simulate(True)[-1]['issue_count'], 1)
    def test_api_data(self):
        output = run_trace(True)
        self.assertIn(output['source'], ('native','simulated','error'))
        self.assertIn('warning', output)
        self.assertIn('tree', output)
if __name__=='__main__':unittest.main()
