"""Capture TradeSense pages with headless Edge (visual inspection)."""
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

BASE = Path(__file__).resolve().parent.parent
SHOTS = BASE / "docs" / "phase1-screenshots"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BACKEND_PORT = os.environ.get("TRADESENSE_BACKEND_PORT", "8001")
FRONTEND_PORT = os.environ.get("TRADESENSE_FRONTEND_PORT", "5173")
API = f"http://127.0.0.1:{BACKEND_PORT}/api"


def token() -> str:
    r = httpx.post(f"{API}/auth/login", json={
        "email": "demo@tradesense-demo.cn", "password": "demo1234"})
    return r.json()["access_token"]


def find_inquiry(t: str, q: str) -> int:
    r = httpx.get(f"{API}/inquiries", params={"q": q}, headers={"Authorization": f"Bearer {t}"})
    return r.json()["items"][0]["id"]


def capture(tk: str, name: str, path: str) -> None:
    out = SHOTS / f"{name}.png"
    url = f"http://127.0.0.1:{FRONTEND_PORT}/#token={tk}&next={path}"
    tmp = os.environ.get("TEMP") or os.environ.get("tmp") or "/tmp"
    cmd = [
        EDGE, "--headless=new", "--disable-gpu",
        f"--user-data-dir={Path(tmp) / f'edge-hl-{name}'}",
        "--window-size=1440,900", "--virtual-time-budget=15000",
        f"--screenshot={out}", url,
    ]
    # 无头渲染偶发在预算内没完成（截图只有几 KB），重试一次
    for attempt in (1, 2):
        subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if out.exists() and out.stat().st_size > 10000:
            print(f"OK {name} ({out.stat().st_size} bytes{', retry' if attempt > 1 else ''})")
            return
    print(f"FAIL {name} ({out.stat().st_size if out.exists() else 0} bytes)")
    if out.exists():
        os.remove(out)  # 别留半张图误导人


def main() -> None:
    SHOTS.mkdir(exist_ok=True)
    tk = token()
    iid = find_inquiry(tk, "German market")
    pages = [
        ("01-login", "/login"),
        ("02-dashboard", "/"),
        ("03-inquiry-detail", f"/inquiries/{iid}"),
        ("04-products", "/products"),
        ("05-inquiry-list", "/inquiries"),
        ("06-connectors", "/connectors"),
        ("07-analytics", "/analytics"),
        ("08-import", "/products/import"),
        ("09-glossary", "/glossary"),
        ("10-followups", "/followups"),
        ("11-knowledge", "/knowledge"),
        ("13-shipment-detail", "/shipments/1"),
    ]
    for name, path in pages:
        capture(tk, name, path)
        time.sleep(0.5)


if __name__ == "__main__":
    sys.exit(main())
