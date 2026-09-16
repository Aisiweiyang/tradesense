"""Backup the SQLite database (and uploaded documents) into backups/ with a timestamp.

Uses the sqlite3 online-backup API so the copy is consistent even if the app
is writing. Keeps the most recent 10 backups.
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC_DB = BASE / "backend" / "data" / "tradesense.db"
SRC_DOCS = BASE / "backend" / "data" / "documents"
DEST = BASE / "backups"
KEEP = 10


def backup_db(target_dir: Path) -> None:
    src = sqlite3.connect(SRC_DB)
    dst = sqlite3.connect(target_dir / "tradesense.db")
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def main() -> int:
    if not SRC_DB.exists():
        print(f"未找到数据库：{SRC_DB}")
        return 1
    DEST.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = DEST / stamp
    target.mkdir()
    backup_db(target)
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
