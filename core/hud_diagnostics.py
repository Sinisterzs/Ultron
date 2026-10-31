"""Bounded HUD measurements; CSV output only on the existing reporting clock."""
from collections import deque
import csv
from datetime import datetime
from pathlib import Path


class HudDiagnostics:
    FIELDS = ("time", "target_fps", "frame_samples", "effective_fps", "frame_p50_ms",
              "frame_p95_ms", "frame_p99_ms", "frame_max_ms", "gaps_over_1_5_budget",
              "missed_slots", "tick_p95_ms", "lateness_p95_ms", "render_p95_ms",
              "render_max_ms", "blit_p95_ms", "paint_p95_ms", "paint_max_ms",
              "paints_over_budget", "restore_p95_ms", "cache_reuses", "cache_rebuilds",
              "cache_mib", "process_rss_mib")

    def __init__(self, path):
        self.path = Path(path)
        self.buckets = {}
        self.last_tick = self.last_frame = None
        self.active_target = None

    def _bucket(self, target):
        if self.active_target != target:
            self.last_tick = self.last_frame = None
            self.active_target = target
        if target not in self.buckets:
            self.buckets[target] = {name: deque(maxlen=4096) for name in
                                    ("frames", "ticks", "late", "render", "blit", "paint", "restore")}
            self.buckets[target].update(reuses=0, rebuilds=0, missed=0, cache_bytes=0)
        return self.buckets[target]

    def suspend(self):
        self.last_tick = self.last_frame = None

    def tick(self, now, target, lateness_ms, missed):
        bucket = self._bucket(target)
        if self.last_tick is not None:
            bucket["ticks"].append((now - self.last_tick) * 1000)
        self.last_tick = now
        bucket["late"].append(max(0, lateness_ms))
        bucket["missed"] += missed

    def frame(self, now, target, render_ms, rebuilt, cache_bytes):
        bucket = self._bucket(target)
        if self.last_frame is not None:
            bucket["frames"].append((now - self.last_frame) * 1000)
        self.last_frame = now
        bucket["render"].append(render_ms)
        bucket["rebuilds"] += int(rebuilt)
        bucket["cache_bytes"] = cache_bytes

    def blit(self, target, elapsed_ms, reused, total_ms=None):
        bucket = self._bucket(target)
        bucket["blit"].append(elapsed_ms)
        bucket["reuses"] += int(reused)
        if total_ms is not None:
            bucket["restore" if reused else "paint"].append(total_ms)

    @staticmethod
    def percentile(values, fraction):
        ordered = sorted(values)
        return round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))], 3) if ordered else 0

    def rows(self, rss_bytes=0):
        for target, bucket in self.buckets.items():
            frames = bucket["frames"]
            total = sum(frames)
            p = self.percentile
            yield (datetime.now().isoformat(timespec="seconds"), target, len(frames),
                   round(len(frames) * 1000 / total, 3) if total else 0,
                   p(frames, .5), p(frames, .95), p(frames, .99), p(frames, 1),
                   sum(t > 1500 / target for t in frames), bucket["missed"],
                   p(bucket["ticks"], .95), p(bucket["late"], .95),
                   p(bucket["render"], .95), p(bucket["render"], 1),
                   p(bucket["blit"], .95), p(bucket["paint"], .95), p(bucket["paint"], 1),
                   sum(t > 1000 / target for t in bucket["paint"]), p(bucket["restore"], .95),
                   bucket["reuses"], bucket["rebuilds"],
                   round(bucket["cache_bytes"] / 1048576, 3), round(rss_bytes / 1048576, 3))

    def flush(self):
        if not self.buckets:
            return
        # No RSS lookup, sorting or filesystem writes in the frame callbacks.
        try:
            import psutil
            rss = psutil.Process().memory_info().rss
            self.path.parent.mkdir(parents=True, exist_ok=True)
            new_file = not self.path.exists() or self.path.stat().st_size == 0
            with self.path.open("a", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                if new_file:
                    writer.writerow(self.FIELDS)
                writer.writerows(self.rows(rss))
        except (OSError, psutil.Error) as error:
            print(f"[HUD] Falha ao salvar diagnóstico: {error}")
        finally:
            self.buckets.clear()
