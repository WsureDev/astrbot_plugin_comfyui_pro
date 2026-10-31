"""Channel-scoped history preferences and bounded execution request queues."""

import copy
import json
from collections import deque
from pathlib import Path


class ChannelState:
    RECORD_LIMIT = 20

    def __init__(self, history_path: Path):
        self.history_path = history_path
        self.history_channels: set[str] = set()
        self.records: dict[str, deque[dict]] = {}
        if history_path.exists():
            channels = json.loads(history_path.read_text(encoding="utf-8"))
            if not isinstance(channels, list) or not all(isinstance(key, str) for key in channels):
                raise ValueError("渠道历史配置必须是渠道键列表")
            self.history_channels = set(channels)

    def keep_history(self, channel: str) -> bool:
        return channel in self.history_channels

    def set_keep_history(self, channel: str, enabled: bool) -> None:
        channels = self.history_channels.copy()
        if enabled:
            channels.add(channel)
        else:
            channels.discard(channel)
        temporary = self.history_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(sorted(channels), ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.history_path)
        self.history_channels = channels

    def append_record(self, channel: str, record: dict) -> None:
        queue = self.records.setdefault(channel, deque(maxlen=self.RECORD_LIMIT))
        queue.append(copy.deepcopy(record))

    def read_records(self, channel: str, pop_count: int = 0) -> list[dict]:
        queue = self.records.get(channel)
        if not queue:
            return []
        if pop_count:
            records = [queue.popleft() for _ in range(min(pop_count, len(queue)))]
            if not queue:
                del self.records[channel]
            return records
        return copy.deepcopy(list(queue))

    def record_count(self, channel: str) -> int:
        return len(self.records.get(channel, ()))
