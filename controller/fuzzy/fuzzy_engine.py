import json
import logging
from typing import Any, Dict, List, Optional
import numpy as np

logger = logging.getLogger(__name__)


def trimf(x: float, a: float, b: float, c: float) -> float:
    """Triangular membership function."""
    if x <= a or x >= c:
        return 0.0
    if a < x <= b:
        return (x - a) / (b - a) if b != a else 1.0
    if b < x < c:
        return (c - x) / (c - b) if c != b else 1.0
    return 0.0


def trapmf(x: float, a: float, b: float, c: float, d: float) -> float:
    """Trapezoidal membership function with shoulder support."""
    if x < a or x > d:
        return 0.0
    if a <= x < b:
        return (x - a) / (b - a) if b != a else 1.0
    if b <= x <= c:
        return 1.0
    if c < x <= d:
        return (d - x) / (d - c) if d != c else 1.0
    return 0.0


class FuzzyEngine:
    """27-rule Mamdani Fuzzy Inference System for adaptive warm-capacity control."""

    def __init__(self, config_path: str = "configs/fuzzy_rules.json", resolution: int = 201):
        self.resolution = resolution
        self.u_output = np.linspace(0.0, 1.0, resolution)
        self.rules: List[Dict[str, Any]] = []
        self.mf_specs: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._load_config(config_path)
        self._precompute_output_curves()

    def _load_config(self, config_path: str):
        with open(config_path, "r") as f:
            data = json.load(f)
        self.mf_specs = data.get("membership_functions", {})
        self.rules = data.get("rules", [])

    def _precompute_output_curves(self):
        """Precomputes discrete membership values for output linguistic terms."""
        self.output_curves: Dict[str, np.ndarray] = {}
        p_terms = self.mf_specs.get("P", {})
        for term, spec in p_terms.items():
            m_type = spec["type"]
            params = spec["params"]
            if m_type == "trimf":
                curve = np.array([trimf(u, params[0], params[1], params[2]) for u in self.u_output])
            elif m_type == "trapmf":
                curve = np.array([trapmf(u, params[0], params[1], params[2], params[3]) for u in self.u_output])
            else:
                curve = np.zeros_like(self.u_output)
            self.output_curves[term] = curve

    def _eval_input_mf(self, var_name: str, term_name: Optional[str], x: float) -> float:
        if term_name is None or term_name == "—" or term_name == "-":
            return 1.0  # Don't-care condition
        spec = self.mf_specs.get(var_name, {}).get(term_name)
        if not spec:
            return 0.0
        m_type = spec["type"]
        params = spec["params"]
        if m_type == "trimf":
            return trimf(x, params[0], params[1], params[2])
        elif m_type == "trapmf":
            return trapmf(x, params[0], params[1], params[2], params[3])
        return 0.0

    def evaluate(self, R: float, T: float, C: float, M: float) -> float:
        """Evaluates inputs R in [0,1], T in [-1,1], C in [0,1], M in [0,1] -> P in [0,1]."""
        # Clamp inputs to their domains
        r_clamped = min(max(float(R), 0.0), 1.0)
        t_clamped = min(max(float(T), -1.0), 1.0)
        c_clamped = min(max(float(C), 0.0), 1.0)
        m_clamped = min(max(float(M), 0.0), 1.0)

        aggregated = np.zeros_like(self.u_output)
        any_fired = False

        for rule in self.rules:
            mu_r = self._eval_input_mf("R", rule.get("R"), r_clamped)
            mu_t = self._eval_input_mf("T", rule.get("T"), t_clamped)
            mu_c = self._eval_input_mf("C", rule.get("C"), c_clamped)
            mu_m = self._eval_input_mf("M", rule.get("M"), m_clamped)

            # Min-AND antecedent firing strength
            weight = min(mu_r, mu_t, mu_c, mu_m)
            if weight > 1e-6:
                any_fired = True
                out_term = rule.get("P", "MEDIUM")
                term_curve = self.output_curves.get(out_term, np.zeros_like(self.u_output))
                # Min implication
                rule_output = np.minimum(weight, term_curve)
                # Max aggregation
                aggregated = np.maximum(aggregated, rule_output)

        if not any_fired or np.sum(aggregated) == 0.0:
            return 0.5  # Neutral default

        # Centroid Defuzzification
        centroid = float(np.sum(self.u_output * aggregated) / np.sum(aggregated))
        return min(max(centroid, 0.0), 1.0)

    def scale_to_instances(self, p_fuzzy: float, min_inst: int = 0, max_inst: int = 10) -> int:
        """Scales continuous [0, 1] recommendation to integer container count."""
        raw_val = min_inst + p_fuzzy * (max_inst - min_inst)
        return int(round(raw_val))
