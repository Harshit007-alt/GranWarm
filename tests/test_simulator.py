import unittest
from simulator.env import SimEnvironment


class TestSimulator(unittest.TestCase):
    def test_simulator_cold_vs_warm(self):
        """First invocation should be cold; subsequent invocation with warm pool should be warm."""
        env = SimEnvironment("configs/dependencies.json")
        r1 = env.step_invoke("f01", 1.0)
        self.assertTrue(r1.is_cold_start)
        self.assertGreaterEqual(r1.latency_ms, 150.0)

        # Prewarm F1 container
        env.set_prewarm_policy({"f01": 2})
        r2 = env.step_invoke("f01", 2.0)
        self.assertFalse(r2.is_cold_start)
        self.assertLess(r2.latency_ms, 100.0)

    def test_granularity_layer_cache_reduces_cold(self):
        """Prewarming shared runtime should reduce cold-start latency for dependent functions."""
        env = SimEnvironment("configs/dependencies.json")
        r_no_cache = env.step_invoke("f03", 1.0)

        env.reset()
        env.set_prewarm_policy({"f03": 0}, tree_targets={"python_311": 1})
        r_with_cache = env.step_invoke("f03", 1.0)

        self.assertLess(r_with_cache.latency_ms, r_no_cache.latency_ms)


if __name__ == "__main__":
    unittest.main()
