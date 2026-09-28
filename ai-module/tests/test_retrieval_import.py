import subprocess
import sys
import unittest
from pathlib import Path


class RetrievalImportTest(unittest.TestCase):
    def test_hybrid_search_imports_without_core_package_cycle(self):
        module_root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from tools.hybrid_search import HybridSearcher; print(HybridSearcher.__name__)",
            ],
            cwd=module_root,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("HybridSearcher", result.stdout)


if __name__ == "__main__":
    unittest.main()
