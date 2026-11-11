"""Unit tests for the Cloudflare Worker download analytics and short links."""
import subprocess
from pathlib import Path


def test_worker_analytics_and_redirects():
    script = Path(__file__).parent / "worker.test.js"
    result = subprocess.run(
        ["node", "--test", str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Worker tests failed:\n{result.stdout}\n{result.stderr}"
