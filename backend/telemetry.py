"""Thread-safe incident store: daily counter, last incident, alert feed, per-label cooldown."""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date


@dataclass(slots=True)
class Alert:
    id: int
    ts: float
    kind: str        # "threat" | "panic" | "system"
    severity: str    # "critical" | "warning" | "info"
    message: str
    source: str | None = None
    label: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class TelemetryStore:
    def __init__(self, cooldown_s: float = 6.0, max_alerts: int = 300) -> None:
        self._cooldown = cooldown_s
        self._lock = threading.Lock()
        self._alerts: deque[Alert] = deque(maxlen=max_alerts)
        self._next_id = 1
        self._day = date.today()
        self._threats_today = 0
        self._last_incident: Alert | None = None
        self._last_by_key: dict[tuple[str, str], float] = {}

    def _roll_day(self) -> None:
        today = date.today()
        if today != self._day:
            self._day, self._threats_today, self._last_incident = today, 0, None

    def _append(self, **fields) -> Alert:
        alert = Alert(id=self._next_id, ts=time.time(), **fields)
        self._next_id += 1
        self._alerts.append(alert)
        return alert

    def record_threat(self, label: str, confidence: float, source: str) -> Alert | None:
        """Log a confirmed threat. Returns None if suppressed by the per-source/label cooldown."""
        now = time.time()
        key = (source, label.lower())
        with self._lock:
            self._roll_day()
            if now - self._last_by_key.get(key, 0.0) < self._cooldown:
                return None
            self._last_by_key[key] = now
            self._threats_today += 1
            alert = self._append(
                kind="threat", severity="critical", source=source, label=label,
                confidence=confidence,
                message=f"{label.title()} detected ({confidence * 100:.0f}%)",
            )
            self._last_incident = alert
            return alert

    def record_event(self, kind: str, severity: str, message: str, source: str | None = None) -> Alert:
        with self._lock:
            self._roll_day()
            return self._append(kind=kind, severity=severity, message=message, source=source)

    def snapshot(self, limit: int = 40) -> dict:
        with self._lock:
            self._roll_day()
            return {
                "date": self._day.isoformat(),
                "total_threats": self._threats_today,
                "last_incident": self._last_incident.to_dict() if self._last_incident else None,
                "alerts": [a.to_dict() for a in list(self._alerts)[::-1][:limit]],
                "server_time": time.time(),
            }
