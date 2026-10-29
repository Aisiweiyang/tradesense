"""Apply migrations, then seed only when explicitly enabled by settings.

A failed migration stops startup. Never stamp an unknown schema as up-to-date.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    backend_dir = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_dir))

    def alembic(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=str(backend_dir),
                              capture_output=True, text=True)

    result = alembic("upgrade", "head")
    if result.returncode != 0:
        print("[init_db] migration failed; startup stopped. Back up and inspect the database before retrying.", file=sys.stderr)
        print(result.stderr[-2000:], file=sys.stderr)
        return 1
    print("[init_db] alembic upgrade head: ok")

    from app.config import settings
    if not settings.seed_demo_data:
        print("[init_db] demo seed disabled; use the first-run setup screen to create an administrator")
        return 0
    from app.seed.run import ensure_seeded
    seeded = ensure_seeded()
    print(f"[init_db] demo seed {'done' if seeded else 'already present'}")
    print("[init_db] demo account: demo@tradesense-demo.cn / demo1234")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
