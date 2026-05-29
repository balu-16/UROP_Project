import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.update(
        {
            "MONGODB_URL": "memory://tests",
            "MONGODB_DB_NAME": "ragnostic_tests",
            "OPENROUTER_API_KEY": "",
            "MOCK_OPENROUTER": "true",
            "DISABLE_LOCAL_MODELS": "true",
            "STORAGE_DIR": str(root / "storage_test"),
            "JWT_SECRET": "test-secret-with-enough-length",
        }
    )
    return subprocess.call([sys.executable, "-m", "pytest", "-q", "tests"], cwd=root, env=env)


if __name__ == "__main__":
    raise SystemExit(main())

