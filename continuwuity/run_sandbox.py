import subprocess, tempfile, os

DENO = os.environ.get("DENO_PATH", "deno")

def run_js(code, timeout=5):
    """Run JS code in Deno sandbox (no permissions). Returns (passed, output)."""
    with tempfile.NamedTemporaryFile(suffix=".js", mode="w", delete=False) as f:
        f.write(code)
        f.flush()
        try:
            result = subprocess.run(
                [DENO, "run", "--no-prompt", f.name],
                capture_output=True, text=True, timeout=timeout,
            )
            output = result.stdout + result.stderr
            passed = result.returncode == 0 and "PASS" in result.stdout
            return passed, output.strip()
        except subprocess.TimeoutExpired:
            return False, "Execution timed out"
        finally:
            os.unlink(f.name)
