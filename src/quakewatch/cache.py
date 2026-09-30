"""TTL response cache; corrupt entries are treated as misses."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast


class ResponseCache:
    def __init__(
        self, directory: Path = Path(".cache/quakewatch"), ttl: float = 300, enabled: bool = True
    ) -> None:
        if not math.isfinite(ttl) or ttl < 0:
            raise ValueError("Cache TTL must be finite and nonnegative")
        self.directory = directory
        self.ttl = ttl
        self.enabled = enabled

    def get(self, key: str, loader: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        if not self.enabled or self.ttl == 0:
            return loader()
        path = self.directory / (hashlib.sha256(key.encode()).hexdigest() + ".json")
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
            age = time.time() - entry["saved_at"]
            if 0 <= age < self.ttl and isinstance(entry["response"], dict):
                return cast(dict[str, Any], entry["response"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        response = loader()
        self.directory.mkdir(parents=True, exist_ok=True)
        # Atomic replacement keeps simultaneous CLI processes from reading partial files.
        temp: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.directory, delete=False
            ) as handle:
                temp = handle.name
                json.dump({"saved_at": time.time(), "response": response}, handle, allow_nan=False)
            os.replace(temp, path)
        finally:
            if temp is not None:
                Path(temp).unlink(missing_ok=True)
        return response
