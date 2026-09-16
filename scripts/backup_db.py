"""Backup the SQLite database (and document files) into backups/ with a timestamp.

Keeps the most recent 10 backups by default. Run while the app is stopped, or
accept the tiny risk of copying mid-write (SQLite hot copy is usually fine for
this scale).
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC_DB = BASE / "backend" / "data" / "tradesense.db"
SRC_DOCS = BASE / "backend" / "data" / "documents"
DEST = BASE / "backups"
KEEP = 10


def main() -> int:
    if not SRC_DB.exists():
        print(f"未找到数据库：{SRC_DB}")
        return 1
    DEST.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = DEST / stamp
    target.mkdir()
    shutil.copy2(SRC_DB, target / "tradesense.db")
    if SRC_DOCS.exists():
        shutil.copytree(SRC_DOCS, target / "documents")
    print(f"备份完成 → {target}")

    backups = sorted(d for d in DEST.iterdir() if d.is_dir())
    for old in backups[:-KEEP]:
        shutil.rmtree(old)
        print(f"清理旧备份 {old.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
