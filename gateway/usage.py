"""Licznik dziennego zuzycia tokenow per klient + audit log JSONL (odtwarzany po restarcie)."""
import json
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


class Usage:
    def __init__(self, path: str):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.totals: dict[tuple[str, str], int] = defaultdict(int)  # (dzien, klient) -> tokeny
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
                self.totals[(e["ts"][:10], e["client"])] += e.get("input_tokens", 0) + e.get("output_tokens", 0)
            except (ValueError, KeyError):
                continue

    @staticmethod
    def today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def used(self, client: str) -> int:
        return self.totals[(self.today(), client)]

    def record(self, client: str, **fields):
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "client": client, **fields}
        with self.lock:
            self.totals[(entry["ts"][:10], client)] += fields.get("input_tokens", 0) + fields.get("output_tokens", 0)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def summary(self) -> dict:
        day = self.today()
        return {c: t for (d, c), t in self.totals.items() if d == day}
