from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class TelemetryRegistry:
    counters: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    latencies_ms: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))

    def inc(self, name: str, value: int = 1) -> None:
        self.counters[name] += value

    def observe_ms(self, name: str, value: float) -> None:
        self.latencies_ms[name].append(float(value))

    @contextmanager
    def timer(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
            self.inc(name + ".success")
        except Exception:
            self.inc(name + ".error")
            raise
        finally:
            self.observe_ms(name + ".latency_ms", (time.perf_counter() - start) * 1000)

    def snapshot(self) -> dict[str, object]:
        latency_summary: dict[str, dict[str, float]] = {}
        for name, values in self.latencies_ms.items():
            if not values:
                continue
            latency_summary[name] = {
                "count": len(values),
                "avg": sum(values) / len(values),
                "max": max(values),
            }
        return {"counters": dict(self.counters), "latencies_ms": latency_summary}

    def prometheus_text(self) -> str:
        lines: list[str] = []
        for name, value in sorted(self.counters.items()):
            metric = "super_memory_" + name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {metric} counter")
            lines.append(f"{metric} {value}")
        for name, values in sorted(self.latencies_ms.items()):
            if not values:
                continue
            metric = "super_memory_" + name.replace(".", "_").replace("-", "_")
            lines.append(f"# TYPE {metric} gauge")
            lines.append(f"{metric}_avg {sum(values) / len(values):.3f}")
            lines.append(f"{metric}_max {max(values):.3f}")
            lines.append(f"{metric}_count {len(values)}")
        return "\n".join(lines) + ("\n" if lines else "")


telemetry = TelemetryRegistry()
