import unittest
from controller.monitor.prometheus_client import PrometheusMonitor


class TestMonitor(unittest.TestCase):
    def test_signal_extraction_bounds(self):
        """Signals R_i, T_i, C_i, M must remain strictly inside normalized ranges."""
        pm = PrometheusMonitor(enable_mock_fallback=True)
        metrics = pm.get_function_metrics("f01-hello-world")

        self.assertIn("R_i", metrics)
        self.assertIn("T_i", metrics)
        self.assertIn("C_i", metrics)
        self.assertIn("M", metrics)

        self.assertTrue(0.0 <= metrics["R_i"] <= 1.0, f"R_i out of range: {metrics['R_i']}")
        self.assertTrue(-1.0 <= metrics["T_i"] <= 1.0, f"T_i out of range: {metrics['T_i']}")
        self.assertTrue(0.0 <= metrics["C_i"] <= 1.0, f"C_i out of range: {metrics['C_i']}")
        self.assertTrue(0.0 <= metrics["M"] <= 1.0, f"M out of range: {metrics['M']}")


if __name__ == "__main__":
    unittest.main()
