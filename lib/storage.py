"""
去重存储：用 JSON 文件记录已处理的推文 ID。
每次运行会自动加载历史记录，处理完后保存。
"""

import json
import os
from pathlib import Path
from typing import Set


class Storage:
    """管理已处理推文 ID 的持久化存储。"""

    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.data_dir / "seen_tweets.json"
        self.seen_ids: Set[str] = set()
        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        """从文件加载已处理的推文 ID。"""
        if not self.file_path.exists():
            return
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
            self.seen_ids = set(data.get("ids", []))
        except (json.JSONDecodeError, KeyError):
            print("⚠️ seen_tweets.json 损坏，从头开始")

    # ------------------------------------------------------------------
    def is_seen(self, tweet_id: str) -> bool:
        """推文是否已处理过。"""
        return tweet_id in self.seen_ids

    # ------------------------------------------------------------------
    def mark_seen(self, tweet_id: str) -> None:
        """标记推文为已处理。"""
        self.seen_ids.add(tweet_id)

    # ------------------------------------------------------------------
    def save(self) -> None:
        """保存到文件，只保留最近 5000 条记录。"""
        ids = sorted(self.seen_ids)[-5000:]
        self.file_path.write_text(
            json.dumps({"ids": ids, "count": len(ids)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"💾 去重记录已保存 ({len(ids)} 条)")
