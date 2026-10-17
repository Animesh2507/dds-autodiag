import unittest
from unittest.mock import patch

from autodiag import bench, rviz_agent


def plan(*actions, notes=()):
    return {'summary': '', 'notes': list(notes), 'rejected': [], 'actions': list(actions)}


class BenchTests(unittest.TestCase):
    def test_scenarios_are_well_formed(self):
        self.assertEqual(len({s['id'] for s in bench.SCENARIOS}), len(bench.SCENARIOS))
        for s in bench.SCENARIOS:
            for c in s['checks']:
                self.assertTrue('note' in c or c['action'] in rviz_agent.ACTIONS, (s['id'], c))

    def test_score_matches_fields_regexes_and_notes(self):
        sc = next(s for s in bench.SCENARIOS if s['id'] == 'light_weight')
        good = plan({'action': 'set_property', 'display': 'PointCloud', 'property': 'Decay Time', 'value': '0'},
                    notes=['True downsampling needs a filter node such as pcl_ros VoxelGrid.'])
        self.assertEqual(bench.score(sc, good)['passed'], 2)
        bad = plan({'action': 'set_property', 'display': 'Grid', 'property': 'Alpha', 'value': '0.5'})
        self.assertEqual(bench.score(sc, bad)['passed'], 0)

    def test_run_scores_the_final_plan_and_summarizes(self):
        sc = next(s for s in bench.SCENARIOS if s['id'] == 'hide_rename')
        answer = plan({'action': 'set_enabled', 'display': 'Grid', 'value': 'false'},
                      {'action': 'rename_display', 'display': 'LaserScan', 'value': 'Front lidar'})
        answer['usage'] = {'prompt_tokens': 900, 'output_tokens': 80}
        with patch('autodiag.rviz_agent.plan_with_context', return_value=answer):
            report = bench.run([('ollama', 'qwen3:4b-instruct')], ['hide_rename'])
        r = report['results'][0]
        self.assertEqual((r['scenarios_passed'], r['checks_passed'], r['checks']), (1, 2, 2))
        self.assertEqual(r['mean_prompt_tokens'], 900)
        self.assertIn('| ollama · `qwen3:4b-instruct` | 1/1 | 2/2 |', bench.markdown(report))
        self.assertEqual(report['scenarios'][0]['id'], sc['id'])

    def test_provider_errors_count_as_failures(self):
        with patch('autodiag.rviz_agent.plan_with_context', side_effect=rviz_agent.PlanError('no credits')):
            report = bench.run([('openai', 'gpt-5-mini')], ['camera'])
        r = report['results'][0]
        self.assertEqual((r['errors'], r['scenarios_passed'], r['median_seconds']), (1, 0, None))


if __name__ == '__main__':
    unittest.main()
