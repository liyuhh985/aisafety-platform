import subprocess
import sys
from pathlib import Path


def test_cli_check_only_validates_manifest():
    root = Path(__file__).parents[2]
    result = subprocess.run(
        [sys.executable, "tools/build_interview_code_walkthrough.py", "--check-only"],
        cwd=root,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert "9 chapters" in result.stdout
    assert "34 snippets" in result.stdout
