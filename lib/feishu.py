"""
飞书分发模块。

功能:
1. 获取 tenant_access_token（用 App ID + Secret）
2. 上传图片到飞书图床
3. 通过 Webhook 发送富文本消息到飞书群

前置准备: 在 https://open.feishu.cn 创建应用，开通「机器人」能力。
"""

import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional

# 北京时间 (UTC+8)
CST = timezone(timedelta(hours=8))

import requests


class Feishu:
    """飞书机器人：上传图片 + 推送消息（支持多群）。"""

    def __init__(self, app_id: str, app_secret: str, webhook_url: str | list[str]):
        self.app_id = app_id
        self.app_secret = app_secret
        # 统一转为列表，支持单个或多个 webhook
        self.webhooks = [webhook_url] if isinstance(webhook_url, str) else webhook_url
        self._token: Optional[str] = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    def _get_token(self) -> str:
        """获取或续期 tenant_access_token（有效期 2 小时）。"""
        if self._token and time.time() < self._token_expiry:
            return self._token

        resp = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        code = data.get("code", -1)
        if code != 0:
            raise RuntimeError(f"飞书认证失败: {data.get('msg', data)}")

        self._token = data["tenant_access_token"]
        # 提前 5 分钟过期，避免边界问题
        self._token_expiry = time.time() + data.get("expire", 7200) - 300
        return self._token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    def upload_image(self, image_bytes: bytes) -> str:
        """
        上传图片到飞书图床。

        Returns
        -------
        str : image_key，用于在消息中嵌入图片
        """
        token = self._get_token()

        resp = requests.post(
            "https://open.feishu.cn/open-apis/im/v1/images",
            headers={"Authorization": f"Bearer {token}"},
            files={"image": ("tweet_image.jpg", image_bytes, "image/jpeg")},
            data={"image_type": "message"},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        code = data.get("code", -1)
        if code != 0:
            raise RuntimeError(f"飞书图片上传失败: {data.get('msg', data)}")

        return data["data"]["image_key"]

    # ------------------------------------------------------------------
    def send_post(
        self,
        original_text: str,
        translated_text: str,
        tweet_url: str,
        created_at: datetime,
        author: str = "Serenity",
        image_keys: Optional[List[str]] = None,
        title_prefix: str = "📢 新推文",
    ) -> bool:
        """
        发送富文本消息（原文 + 翻译 + 图片）到飞书群。

        使用飞书「post」消息格式，支持：
        - 加粗标题
        - 分段文字
        - 超链接
        - 图片嵌入
        """
        image_keys = image_keys or []

        # 转换为北京时间
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        time_str = created_at.astimezone(CST).strftime("%Y-%m-%d %H:%M CST")

        # 构建消息段落
        content_blocks: list = []

        # ---- 文字段落 ----
        text_paragraph = [
            {"tag": "text", "text": f"🕐 {time_str}\n\n"},
            {"tag": "text", "text": "【原文】\n"},
            {"tag": "text", "text": f"{original_text}\n\n"},
            {"tag": "text", "text": "【中文翻译】\n"},
            {"tag": "text", "text": f"{translated_text}\n\n"},
            {"tag": "a", "text": "🔗 在 X 上查看原文", "href": tweet_url},
        ]
        content_blocks.append(text_paragraph)

        # ---- 图片段落（每张图独立一行） ----
        for img_key in image_keys:
            content_blocks.append([
                {"tag": "img", "image_key": img_key}
            ])

        payload = {
            "msg_type": "post",
            "content": {
                "post": {
                    "zh_cn": {
                        "title": f"{title_prefix} @{author}",
                        "content": content_blocks,
                    }
                }
            },
        }

        all_ok = True
        for i, hook in enumerate(self.webhooks):
            try:
                resp = requests.post(hook, json=payload, timeout=30)
                resp.raise_for_status()
                result = resp.json()

                code = result.get("code", -1)
                if code != 0:
                    print(f"❌ 群{i+1} 发送失败: {result.get('msg', result)}")
                    all_ok = False
                elif len(self.webhooks) > 1:
                    print(f"  ✅ 群{i+1} 发送成功")
            except Exception as exc:
                print(f"❌ 群{i+1} 发送异常: {exc}")
                all_ok = False

        return all_ok
