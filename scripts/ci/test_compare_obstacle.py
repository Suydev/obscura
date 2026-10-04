import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ObstacleReleaseGate(unittest.TestCase):
    def compare(self, candidate_passes):
        stages = [{"name": f"stage-{n}", "pass": True, "median_ms": 1}
                  for n in range(33)]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory) / "base.json"
            candidate = Path(directory) / "candidate.json"
            stages[0]["pass"] = False
            base.write_text(json.dumps({"results": stages}))
            stages[0]["pass"] = candidate_passes
            candidate.write_text(json.dumps({"results": stages}))
            return subprocess.run(
                [sys.executable, str(Path(__file__).with_name("compare_obstacle.py")),
                 "--base", str(base), "--candidate", str(candidate)],
                capture_output=True, text=True,
            )

    def test_shared_baseline_failure_does_not_pass_the_release_gate(self):
        result = self.compare(False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("32/33", result.stdout)

    def test_candidate_fixing_the_baseline_failure_passes(self):
        result = self.compare(True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("33/33", result.stdout)


if __name__ == "__main__":
    unittest.main()
