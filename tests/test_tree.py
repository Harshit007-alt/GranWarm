import unittest
from controller.granularity.tree import GranularityTree


class TestGranularityTree(unittest.TestCase):
    def setUp(self):
        self.tree = GranularityTree("configs/dependencies.json")

    def test_total_nodes(self):
        """Granularity tree must define K=20 total nodes."""
        self.assertEqual(self.tree.get_total_nodes(), 20)

    def test_max_projection(self):
        """Pillow bundle node must take the maximum of F3, F4, F5."""
        recs = {"f03": 0.6, "f04": 0.85, "f05": 0.3}
        projected = self.tree.project_capacities(recs)
        self.assertAlmostEqual(projected["pillow_bundle"], 0.85)

    def test_runtime_inherits_max(self):
        """Runtime nodes must inherit the maximum across all dependent functions."""
        recs = {"f01": 0.2, "f03": 0.9, "f07": 0.4}
        projected = self.tree.project_capacities(recs)
        self.assertAlmostEqual(projected["python_311"], 0.9)
        self.assertAlmostEqual(projected["nodejs_20"], 0.2)

    def test_all_functions_have_paths(self):
        """All 12 functions must have complete non-empty dependency paths."""
        for i in range(1, 13):
            fid = f"f{i:02d}"
            path = self.tree.get_dependency_path(fid)
            self.assertGreaterEqual(len(path), 2, f"Function {fid} path too short: {path}")
            self.assertEqual(path[0], "root")


if __name__ == "__main__":
    unittest.main()
