"""Isolated Qt/crystal comparison; no app imports, credentials or audio.

Run from the repository root. Results describe this fixture, not global app FPS.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import psutil

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from test_hud_frame_cache import HudFrameCacheTests, QtCore, QtGui
from core.hud_diagnostics import HudDiagnostics


def direct_paint(hud, event):
    """Previous direct QWidget path, retaining its original unpaced-paint guard."""
    size = (hud.width(), hud.height())
    if not hud._paint_permit and size == getattr(hud, "_direct_size", None):
        return
    hud._direct_size = size
    hud._paint_permit = False
    start = time.perf_counter()
    painter = QtGui.QPainter(hud)
    try:
        hud._paint_frame(painter)
    finally:
        painter.end()
    hud._hud_probe.frame(start, hud._fps_target, (time.perf_counter() - start) * 1000, False, 0)
    hud._hud_probe.blit(hud._fps_target, 0, False, (time.perf_counter() - start) * 1000)


def run(mode, target, seconds, output):
    fixture = HudFrameCacheTests()
    fixture.setUp()
    hud = fixture.hud
    if mode == "direct":
        type(hud).paintEvent = direct_paint
    hud._fps_target = target
    hud._hud_probe = HudDiagnostics(output / f"{mode}-{target}.csv")
    hud._paint_permit = True
    hud.repaint()
    # An exposure between ticks: old guard drops the drawing, cache restores it.
    snapshot = hud.grab().toImage()
    snapshot.save(str(output / f"{mode}-{target}.png"))
    hud._hud_probe = HudDiagnostics(output / f"{mode}-{target}.csv")
    hud._fps_frames = 0
    hud._fps_since = time.perf_counter()
    hud._fps_next_deadline = time.perf_counter() + 1 / target
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(round(seconds * 1000), loop.quit)
    hud._tmr.start(max(1, round(1000 / target)))
    loop.exec()
    hud._tmr.stop()
    row = dict(zip(hud._hud_probe.FIELDS,
                   list(hud._hud_probe.rows(psutil.Process().memory_info().rss))[0]))
    row["mode"] = mode
    hud._hud_probe.flush()
    fixture.tearDown()
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "tools/reports/hud-cache")
    args = parser.parse_args()
    if not 1 <= args.seconds <= 30:
        parser.error("--seconds must be between 1 and 30")
    args.output = args.output / time.strftime("%Y%m%d-%H%M%S")
    args.output.mkdir(parents=True, exist_ok=True)
    HudFrameCacheTests.setUpClass()
    rows = [run(mode, target, args.seconds, args.output)
            for target in (47, 60) for mode in ("direct", "cached")]
    (args.output / "comparison.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    for row in rows:
        print(row["mode"], row["target_fps"], "FPS:", row["effective_fps"],
              "render p95:", row["render_p95_ms"], "ms; blit p95:", row["blit_p95_ms"], "ms")
    print("Reports:", args.output)


if __name__ == "__main__":
    main()
