import unittest
import numpy as np
from controller.pso.pso_optimizer import DiscreteConstrainedPSO


class TestPSO(unittest.TestCase):
    def test_budget_constraint_enforced(self):
        """Optimal solution must not exceed memory budget."""
        node_mem = np.array([80, 40, 15, 25, 15, 35, 10, 1, 5, 5, 60, 3, 400, 1800, 5, 3, 8, 30, 15, 0])
        budget = 4000.0
        pso = DiscreteConstrainedPSO(
            dimension=20,
            swarm_size=25,
            max_iter=30,
            memory_budget_mb=budget,
            node_memories=node_mem,
            seed=42
        )

        fuzzy_prior = np.ones(20) * 3.0
        best_x = pso.optimize(fuzzy_prior=fuzzy_prior)
        total_mem = np.dot(best_x, node_mem)

        self.assertLessEqual(total_mem, budget, f"Memory budget exceeded: {total_mem} MB > {budget} MB")

    def test_fitness_convergence(self):
        """Best fitness must monotonically improve or stay equal over iterations."""
        node_mem = np.ones(10) * 50.0
        pso = DiscreteConstrainedPSO(
            dimension=10,
            swarm_size=20,
            max_iter=30,
            memory_budget_mb=2000.0,
            node_memories=node_mem,
            seed=123
        )

        best_x, history = pso.optimize(return_history=True)
        self.assertLessEqual(history[-1], history[0], f"PSO did not improve fitness: initial {history[0]}, final {history[-1]}")

    def test_integer_positions(self):
        """All positions must be non-negative integers."""
        pso = DiscreteConstrainedPSO(dimension=5, swarm_size=15, max_iter=20, seed=99)
        best_x = pso.optimize()
        for x in best_x:
            self.assertTrue(isinstance(x, (int, np.integer)) and x >= 0)


if __name__ == "__main__":
    unittest.main()
