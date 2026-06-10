#!/usr/bin/env python3
"""
X Feed Collector —— 采集 @Serenity 的推文 → 翻译 → 推送到飞书

使用方式
--------
1. 本地测试:  cp .env.example .env  → 填写配置 → python main.py
2. 自动运行:  推送到 GitHub，由 Actions 每 30 分钟执行一次

依赖: pip install -r requirements.txt
"""

import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---- Windows 中文系统控制台 UTF-8 兼容 ----
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# 把项目根目录加到 sys.path，方便 lib/ 导入
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.storage import Storage
from lib.x_collector import XCollector
from lib.translator import Translator
from lib.feishu import Feishu

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

load_dotenv(ROOT / ".env")  # 本地开发用；GitHub Actions 里不存在 .env，自动跳过


def _get_env(name: str) -> str:
    """读取环境变量，空值时报错。"""
    val = os.environ.get(name, "").strip()
    if not val:
        print(f"❌ 缺少必要配置: {name}")
        print("   本地: 在 .env 文件中填写")
        print("   GitHub: 在 Settings > Secrets > Actions 中添加")
        sys.exit(1)
    return val


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def download_image(url: str, timeout: int = 30) -> bytes | None:
    """从 URL 下载图片，返回字节数据。"""
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://x.com/",
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.content
    except requests.exceptions.RequestException as exc:
        print(f"  ⚠️ 图片下载失败 [{url[:60]}]: {exc}")
        return None


# ---------------------------------------------------------------------------
# 主逻辑
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 50)
    print("  X Feed Collector — 启动")
    print("=" * 50)

    # ---- 读取配置 ----
    target_username = os.environ.get("TARGET_USERNAME", "Serenity").strip()

    auth_token = _get_env("X_AUTH_TOKEN")
    ct0 = _get_env("X_CT0")

    feishu_app_id = _get_env("FEISHU_APP_ID")
    feishu_app_secret = _get_env("FEISHU_APP_SECRET")
    feishu_webhook = _get_env("FEISHU_WEBHOOK_URL")

    # ---- 初始化 ----
    data_dir = ROOT / "data"
    storage = Storage(data_dir=str(data_dir))
    collector = XCollector(auth_token=auth_token, ct0=ct0)
    translator = Translator()
    feishu = Feishu(
        app_id=feishu_app_id,
        app_secret=feishu_app_secret,
        webhook_url=feishu_webhook,
    )

    # ---- 采集推文 ----
    print(f"\n🔍 正在获取 @{target_username} 的最新推文...")
    tweets = collector.get_recent_tweets(target_username, count=20)
    print(f"   拉取到 {len(tweets)} 条（已过滤转推/回复）")

    # ---- 去重 ----
    new_tweets = [t for t in tweets if not storage.is_seen(t["id"])]
    print(f"   其中 {len(new_tweets)} 条是新推文")

    if not new_tweets:
        print("\n✅ 没有新推文，无需推送。")
        storage.save()
        return

    # ---- 逐条处理 ----
    success = 0

    for i, tweet in enumerate(new_tweets, 1):
        tid = tweet["id"]
        text = tweet["text"]
        url = tweet["url"]
        created = tweet.get("created_at") or datetime.utcnow()
        images = tweet.get("images", [])

        print(f"\n{'─' * 40}")
        print(f"[{i}/{len(new_tweets)}] {tid}")
        print(f"原文: {text[:100]}{'...' if len(text) > 100 else ''}")

        # ① 翻译
        translated = translator.translate(text, source_lang="en", target_lang="zh-CN")
        print(f"翻译: {translated[:100]}{'...' if len(translated) > 100 else ''}")

        # ② 图片处理：下载 → 上传飞书
        image_keys: list[str] = []
        if images:
            print(f"图片: {len(images)} 张")
            for img_url in images:
                img_bytes = download_image(img_url)
                if img_bytes is None:
                    continue
                try:
                    img_key = feishu.upload_image(img_bytes)
                    image_keys.append(img_key)
                    print(f"  ✅ 上传成功 -> {img_key}")
                except Exception as exc:
                    print(f"  ❌ 上传失败: {exc}")
        else:
            print("图片: 无")

        # ③ 推送到飞书群
        try:
            ok = feishu.send_post(
                original_text=text,
                translated_text=translated,
                tweet_url=url,
                created_at=created,
                author=target_username,
                image_keys=image_keys,
            )
            if ok:
                storage.mark_seen(tid)
                success += 1
                print(f"📤 飞书推送成功！")
            else:
                print(f"❌ 飞书推送失败")
            # 飞书有频率限制，每条消息之间等 2 秒
            time.sleep(2)
        except Exception as exc:
            print(f"❌ 飞书推送异常: {exc}")
            time.sleep(2)

    # ---- 保存去重记录 ----
    storage.save()
    print(f"\n{'=' * 50}")
    print(f"🎉 本轮完成: 成功 {success}/{len(new_tweets)} 条")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
