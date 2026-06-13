#!/usr/bin/env python3
"""
export_pdf.py — 导出付费订阅推文为 PDF

使用 UserSuperFollowTweets GraphQL 查询，获取 @aleabitoreddit 的
付费订阅专属推文 → 翻译为中文 → 生成 PDF（含原文、翻译、图片）。

用法:
    python export_pdf.py [--count N] [--output file.pdf]

依赖: fpdf2 (pip install fpdf2)
"""

import os
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

# ---- Windows 中文系统控制台 UTF-8 兼容 ----
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

# ---- 路径 ----
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lib.x_collector import XCollector, USER_AGENT
from lib.translator import Translator

# ---- 北京时间 ----
CST = timezone(timedelta(hours=8))

# ---- CJK 字体 ----
FONT_URL = (
    "https://github.com/google/fonts/raw/main/ofl/notosanssc/"
    "NotoSansSC%5Bwght%5D.ttf"
)
FONT_DIR = ROOT / "data"
FONT_PATH = FONT_DIR / "NotoSansSC.ttf"


def ensure_cjk_font() -> str:
    """确保 CJK 字体存在（首次自动下载）。"""
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    if not FONT_PATH.exists():
        print(f"🔤 正在下载中文字体（首次运行，约 5MB）...")
        print(f"   来源: Google Fonts (NotoSansSC)")
        try:
            urllib.request.urlretrieve(FONT_URL, FONT_PATH)
            print(f"   ✅ 字体已缓存到: {FONT_PATH}")
        except Exception as exc:
            print(f"   ❌ 字体下载失败: {exc}")
            print(f"   PDF 中的中文可能无法正常显示")
            return ""
    return str(FONT_PATH)


# ---------------------------------------------------------------------------
def download_image(url: str, timeout: int = 30) -> bytes | None:
    """从 URL 下载图片，返回字节数据。"""
    try:
        resp = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
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
#  PDF 构建
# ---------------------------------------------------------------------------

def _build_pdf(
    tweets: list[dict],
    translator: Translator,
    font_path: str,
    output_path: str,
    username: str = "aleaborteddit",
) -> None:
    """用 fpdf2 生成 PDF。"""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    # 注册中文字体
    has_cjk = font_path and Path(font_path).exists()
    if has_cjk:
        pdf.add_font("CJK", "", font_path)
        font_name = "CJK"
    else:
        font_name = "Helvetica"

    total = len(tweets)
    print(f"\n📝 正在生成 PDF（共 {total} 条推文）...")

    for i, tweet in enumerate(tweets, 1):
        tid = tweet["id"]
        text = tweet["text"]
        url = tweet["url"]
        created = tweet.get("created_at") or datetime.utcnow()
        images = tweet.get("images", [])

        # 时间转换
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        time_str = created.astimezone(CST).strftime("%Y-%m-%d %H:%M CST")

        pdf.add_page()

        # ── 标题 ──
        if has_cjk:
            pdf.set_font(font_name, "", 16)
        else:
            pdf.set_font(font_name, "B", 16)
        pdf.cell(0, 10, f"Serenity @{username}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.cell(0, 8, f"订阅专属推文 #{i}/{total}  —  {time_str}", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
        pdf.ln(6)

        # ── 原文 ──
        if has_cjk:
            pdf.set_font(font_name, "", 11)
        else:
            pdf.set_font(font_name, "B", 11)
        pdf.cell(0, 7, "[Original English / 原文]", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        if has_cjk:
            pdf.set_font(font_name, "", 10)
        else:
            pdf.set_font(font_name, "", 10)
        pdf.multi_cell(0, 5.5, text)
        pdf.ln(4)

        # ── 翻译 ──
        translated = translator.translate(text, source_lang="en", target_lang="zh-CN")
        if has_cjk:
            pdf.set_font(font_name, "", 11)
        else:
            pdf.set_font(font_name, "B", 11)
        pdf.cell(0, 7, "[Chinese Translation / 中文翻译]", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)
        if has_cjk:
            pdf.set_font(font_name, "", 10)
        else:
            pdf.set_font(font_name, "", 10)
        pdf.multi_cell(0, 5.5, translated)
        pdf.ln(4)

        # ── 链接 ──
        pdf.set_font(font_name, "", 9)
        pdf.set_text_color(0, 0, 200)
        pdf.cell(0, 6, url, link=url)
        pdf.set_text_color(0, 0, 0)
        pdf.ln(6)

        # ── 图片 ──
        if images:
            for j, img_url in enumerate(images, 1):
                print(f"  [{i}/{total}] 图片 {j}/{len(images)}...", end=" ")
                img_bytes = download_image(img_url)
                if img_bytes is None:
                    print("跳过")
                    continue

                # fpdf2 需要从临时文件加载图片
                with tempfile.NamedTemporaryFile(
                    suffix=".jpg", delete=False
                ) as tmp:
                    tmp.write(img_bytes)
                    tmp_path = tmp.name

                try:
                    # 缩放图片到页面宽度的 80%
                    pdf.image(tmp_path, x=20, w=170)
                    pdf.ln(3)
                    print("✅")
                except Exception as exc:
                    print(f"失败: {exc}")
                finally:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass

        print(f"  ✅ [{i}/{total}] {tid}")

    # ---- 输出 ----
    pdf.output(output_path)
    print(f"\n📄 PDF 已生成: {output_path}")


# ---------------------------------------------------------------------------
#  主入口
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- 配置 ----
    load_dotenv(ROOT / ".env")

    target_username = os.environ.get("TARGET_USERNAME", "aleaborteddit").strip()
    auth_token = os.environ.get("X_AUTH_TOKEN", "").strip()
    ct0 = os.environ.get("X_CT0", "").strip()

    if not auth_token:
        print("❌ 缺少 X_AUTH_TOKEN")
        print("   请在 .env 文件中填写，或设置环境变量")
        sys.exit(1)

    # ---- 解析参数 ----
    # python export_pdf.py [--count N] [--output file.pdf]
    count = 100
    output = "tweets_export_subscriber.pdf"

    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--count" and i + 1 < len(args):
            count = int(args[i + 1])
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output = args[i + 1]
            i += 2
        else:
            i += 1

    # 给输出加时间戳（GitHub Actions 中用）
    if output == "tweets_export_subscriber.pdf":
        ts = datetime.now(CST).strftime("%Y%m%d_%H%M")
        output = f"tweets_export_{ts}.pdf"

    print("=" * 50)
    print("  X Feed Collector — PDF 导出模式")
    print(f"  目标: @{target_username} 订阅专属推文")
    print(f"  数量: 最多 {count} 条")
    print("=" * 50)

    # ---- 初始化 ----
    font_path = ensure_cjk_font()
    collector = XCollector(auth_token=auth_token, ct0=ct0)
    translator = Translator()

    # ---- 翻页拉取订阅专属推文 ----
    all_tweets: list[dict] = []
    cursor: str | None = None
    page = 1

    print(f"\n🔍 正在获取订阅专属推文...")

    while len(all_tweets) < count:
        needed = count - len(all_tweets)
        print(f"   第 {page} 页（已收集 {len(all_tweets)} 条，还需 {needed} 条）...")

        try:
            tweets, cursor = collector.get_super_follow_tweets(
                target_username,
                count=min(needed, 50),
                cursor=cursor,
            )
        except Exception as exc:
            print(f"   ⚠️ 拉取失败: {exc}")
            import traceback
            traceback.print_exc()
            break

        if not tweets:
            print("   📭 没有更多推文了")
            break

        all_tweets.extend(tweets)
        page += 1

        if cursor is None:
            print("   📭 已到最后一页")
            break
        time.sleep(0.5)

    print(f"\n📥 共拉取 {len(all_tweets)} 条订阅专属推文")

    if not all_tweets:
        print("\n⚠️ 没有找到订阅专属推文。")
        print("   请确认:")
        print(f"   1. 该账号已付费订阅 @{target_username}")
        print(f"   2. @{target_username} 开启了订阅功能")
        print("   3. X_AUTH_TOKEN 和 X_CT0 是正确的")
        return

    # ---- 生成 PDF ----
    _build_pdf(all_tweets, translator, font_path, output, username=target_username)

    print(f"\n{'=' * 50}")
    print(f"🎉 PDF 导出完成: {output}")
    print(f"   共 {len(all_tweets)} 条推文")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
