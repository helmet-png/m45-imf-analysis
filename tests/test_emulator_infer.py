"""Regression checks for emulator inference. Run with unittest discover."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "nbody_petar"))
import emulator_infer as infer

class InferenceTests(unittest.TestCase):
    def test_export_preserves_walkers_and_log_prob(self):
        chain = np.arange(4000 * 48 * 2).reshape(-1, 2)
        lp = np.arange(len(chain))
        saved, saved_lp = infer.thin_time_axis(chain, lp, 48)
        self.assertLessEqual(len(saved), 20000)
        self.assertEqual(set(saved_lp % 48), set(range(48)))
        np.testing.assert_array_equal(saved[:, 0], saved_lp * 2)

    def test_sampler_reproducible_despite_global_rng(self):
        def log_prob(x):
            return -0.5 * np.sum(x*x, axis=1)
        args = (log_prob, np.array([-5.]), np.array([5.]), 12, 4000, 1000, 42)
        np.random.seed(1)
        a = infer.sample(*args)
        np.random.seed(987)
        b = infer.sample(*args)
        np.testing.assert_array_equal(a[0], b[0])
        np.testing.assert_array_equal(a[1], b[1])

    def test_short_chain_rejected(self):
        import emcee
        with self.assertRaises(emcee.autocorr.AutocorrError):
            infer.sample(lambda x: -0.5*np.sum(x*x, axis=1),
                         np.array([-5.]), np.array([5.]), 12, 20, 5, 42)

    def test_failed_sbc_does_not_publish_partial_pvalues(self):
        import emcee
        failure = emcee.autocorr.AutocorrError(np.ones(1), "too short")
        with patch.object(infer, "predict_batch", return_value=(np.zeros((1,1)), np.ones((1,1)))), \
             patch.object(infer, "make_log_prob"), \
             patch.object(infer, "sample", side_effect=[
                 (np.zeros((20,1)), None, 0.5, [1.]), failure]):
            result = infer.run_sbc({}, np.eye(1), np.zeros(1), np.ones(1), 2, 12, 20, 5, 42)
        self.assertEqual(result["status"], "incomplete_sampling")
        self.assertEqual(result["n_successful"], 1)
        self.assertEqual(result["per_parameter"], {})
        self.assertEqual(result["ranks"], [])
        self.assertEqual(result["failed_trials"][0]["trial"], 1)

    def test_gp_seed_reproducible(self):
        x = np.linspace(0, 1, 15)[:, None]
        y = (x*x)
        np.random.seed(1)
        a = infer.fit_emulators(x, y, ["a"], random_state=42)
        np.random.seed(987)
        b = infer.fit_emulators(x, y, ["a"], random_state=42)
        np.testing.assert_array_equal(a["emulators"]["a"].kernel_.theta,
                                      b["emulators"]["a"].kernel_.theta)

if __name__ == "__main__":
    unittest.main()
