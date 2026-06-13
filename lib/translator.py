"""
翻译模块（基于 Google Translate）。

使用 deep-translator 库，底层调用 Google Translate 免费接口。
无需 API Key，无需注册，无需信用卡。
"""

from deep_translator import GoogleTranslator


class Translator:
    """Google Translate 英→中翻译器（免费、无需 API Key）。"""

    def __init__(self):
        # GoogleTranslator 是轻量 wrapper，每次调用都是独立的 HTTP 请求
        pass

    # ------------------------------------------------------------------
    def translate(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
    ) -> str:
        """
        翻译一段文本。

        Parameters
        ----------
        text        : 待翻译文本
        source_lang : 源语言（默认 en）
        target_lang : 目标语言（默认 zh-CN = 简体中文）

        Returns
        -------
        str : 翻译后文本（失败时返回原文 + 错误标记）
        """
        if not text or not text.strip():
            return ""

        try:
            result = GoogleTranslator(
                source=source_lang, target=target_lang
            ).translate(text)
            return result

        except Exception as exc:
            print(f"⚠️ Google 翻译失败: {exc}")
            # 如果一次翻译太长导致失败，尝试分段
            if len(text) > 500:
                print("   尝试分段翻译...")
                return self._translate_long(text, source_lang, target_lang)
            return f"[翻译失败，以下为英文原文]\n{text}"

    # ------------------------------------------------------------------
    def _translate_long(
        self,
        text: str,
        source_lang: str = "en",
        target_lang: str = "zh-CN",
    ) -> str:
        """按句子分段翻译，然后拼接。"""
        import re

        # 按句号、换行、问号、感叹号切分
        parts = re.split(r"(?<=[.!?\n])\s+", text)
        results = []
        for part in parts:
            if not part.strip():
                results.append("")
                continue
            try:
                t = GoogleTranslator(
                    source=source_lang, target=target_lang
                ).translate(part)
                results.append(t)
            except Exception:
                results.append(f"[翻译失败]{part[:80]}...")
        return " ".join(results)
