"""Initialize the database: Alembic migration first, create_all as fallback.

Flow:
  1. `alembic upgrade head` — normal path (also upgrades existing DBs).
  2. On failure (fresh DB without alembic support): create_all + `alembic stamp head`
     so future upgrades still work.
  3. Seed demo data once.
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
    if result.returncode == 0:
        print("[init_db] alembic upgrade head: ok")
    else:
        from app.database import engine
        from app.models import Base
        Base.metadata.create_all(bind=engine)
        stamp = alembic("stamp", "head")
        status = "ok" if stamp.returncode == 0 else f"failed: {stamp.stderr[-200:]}"
        print(f"[init_db] create_all fallback applied; alembic stamp head: {status}")

    from app.seed.run import ensure_seeded
    seeded = ensure_seeded()
    print(f"[init_db] demo seed {'done' if seeded else 'already present'}")
    print("[init_db] demo account: demo@tradesense-demo.cn / demo1234")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
