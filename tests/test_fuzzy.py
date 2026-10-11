import unittest
import numpy as np
from controller.fuzzy.fuzzy_engine import FuzzyEngine


class TestFuzzyEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FuzzyEngine("configs/fuzzy_rules.json")

    def test_rule_1_low_traffic_falling(self):
        """Rule 1: LOW invocation + FALLING trend + LOW cold-start -> VERY_LOW."""
        p = self.engine.evaluate(R=0.05, T=-0.8, C=0.05, M=0.2)
        self.assertLess(p, 0.20, f"Expected VERY_LOW capacity, got {p}")

    def test_rule_26_high_traffic_surging(self):
        """Rule 26: HIGH invocation + SURGING trend + LOW memory -> VERY_HIGH."""
        p = self.engine.evaluate(R=0.95, T=0.9, C=0.3, M=0.1)
        self.assertGreater(p, 0.80, f"Expected VERY_HIGH capacity, got {p}")

    def test_memory_pressure_dampens(self):
        """Rule 27 vs 26: HIGH memory pressure dampens target capacity."""
        p_low_mem = self.engine.evaluate(R=0.9, T=0.9, C=0.3, M=0.1)
        p_high_mem = self.engine.evaluate(R=0.9, T=0.9, C=0.3, M=0.95)
        self.assertLess(p_high_mem, p_low_mem, f"High memory should dampen: {p_high_mem} vs {p_low_mem}")

    def test_output_strictly_bounded(self):
        """All 500 random input quadruples must yield output in [0, 1]."""
        rng = np.random.default_rng(42)
        for _ in range(500):
            r = rng.uniform(0.0, 1.0)
            t = rng.uniform(-1.0, 1.0)
            c = rng.uniform(0.0, 1.0)
            m = rng.uniform(0.0, 1.0)
            p = self.engine.evaluate(R=r, T=t, C=c, M=m)
            self.assertTrue(0.0 <= p <= 1.0, f"Output out of bounds: {p}")


if __name__ == "__main__":
    unittest.main()
