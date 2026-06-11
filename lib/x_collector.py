"""
X (Twitter) 推文采集器。

直接用 X GraphQL API + 真实账号 Cookie，无需付费 API Key。
会先从 X 首页自动提取最新的 query ID，避免因 X 更新而过期。
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import requests


# ---- 常量 ----
BEARER_TOKEN = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs"
    "%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# UserSuperFollowTweets 备用 queryId（如果从 main.js 自动提取失败则使用此值）
FALLBACK_SUPER_FOLLOW_QID = "pE3b1z_fFIr0d8VTvWMZjA"


class XCollector:
    """X 推文采集器（直接调用 GraphQL API）。"""

    def __init__(self, auth_token: str, ct0: str = ""):
        self.auth_token = auth_token
        self.ct0 = ct0
        self._session: Optional[requests.Session] = None
        # 缓存的 query ID
        self._user_tweets_qid: Optional[str] = None
        self._user_by_screen_name_qid: Optional[str] = None
        self._super_follow_tweets_qid: Optional[str] = None

    # ------------------------------------------------------------------
    def _build_session(self) -> requests.Session:
        """构建带 Cookie 和 Header 的 requests Session。"""
        s = requests.Session()
        s.headers.update({"User-Agent": USER_AGENT})

        # 以游客身份访问 X 首页获取 guest_id
        try:
            s.get("https://x.com", timeout=30)
        except Exception:
            pass

        # 加上登录 Cookie（用于 GraphQL API 调用）
        s.cookies.set("auth_token", self.auth_token)
        if self.ct0:
            s.cookies.set("ct0", self.ct0)
        s.headers.update({"authorization": f"Bearer {BEARER_TOKEN}"})
        if self.ct0:
            s.headers["x-csrf-token"] = self.ct0
        return s

    @property
    def session(self) -> requests.Session:
        if self._session is None:
            self._session = self._build_session()
        return self._session

    # ------------------------------------------------------------------
    def _refresh_query_ids(self) -> None:
        """从 X 首页 JS 中提取最新的 GraphQL query ID（以游客身份）。"""
        if self._user_tweets_qid and self._user_by_screen_name_qid:
            return

        # 用无认证的临时 session 访问首页获取 JS URL
        tmp = requests.Session()
        tmp.headers.update({"User-Agent": USER_AGENT})
        resp = tmp.get("https://x.com", timeout=30)
        resp.raise_for_status()

        main_js_urls = re.findall(
            r"src=\"(https://abs\.twimg\.com/responsive-web/client-web/main\.[a-f0-9]+\.js)\"",
            resp.text,
        )
        if not main_js_urls:
            raise RuntimeError("无法找到 X 的 main.js，页面结构可能已变更")

        js_resp = tmp.get(main_js_urls[0], timeout=30)
        js_text = js_resp.text

        qid_pattern = re.compile(
            r'\{queryId:"([a-zA-Z0-9_-]{22})",operationName:"(UserTweets|UserByScreenName|UserSuperFollowTweets)"'
        )
        for m in qid_pattern.finditer(js_text):
            op = m.group(2)
            qid = m.group(1)
            if op == "UserTweets":
                self._user_tweets_qid = qid
            elif op == "UserByScreenName":
                self._user_by_screen_name_qid = qid
            elif op == "UserSuperFollowTweets":
                self._super_follow_tweets_qid = qid

        if not self._user_tweets_qid:
            raise RuntimeError("无法提取 UserTweets query ID")
        if not self._user_by_screen_name_qid:
            raise RuntimeError("无法提取 UserByScreenName query ID")
        # UserSuperFollowTweets 不是必需，有备用值

    # ------------------------------------------------------------------
    def _get_user_id(self, username: str) -> str:
        """通过用户名获取 X 用户 ID。"""
        self._refresh_query_ids()

        variables = json.dumps({
            "screen_name": username,
            "withSafetyModeUserFields": True,
        })
        resp = self.session.get(
            f"https://x.com/i/api/graphql/{self._user_by_screen_name_qid}/UserByScreenName",
            params={"variables": variables},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        result = data.get("data", {}).get("user", {}).get("result", {})
        if result.get("__typename") == "UserUnavailable":
            raise RuntimeError(f"用户 @{username} 不存在或被封禁")
        uid = result.get("rest_id")
        if not uid:
            raise RuntimeError(f"无法获取 @{username} 的用户 ID")
        return uid

    # ------------------------------------------------------------------
    #  共享解析逻辑
    # ------------------------------------------------------------------

    def _parse_timeline_instructions(
        self,
        instructions: List[dict],
        username: str,
        count: int,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        解析 GraphQL 返回的 timeline instructions。

        Returns
        -------
        (tweets_list, next_cursor)
            next_cursor 为 None 表示没有更多推文了
        """
        results: List[Dict[str, Any]] = []
        next_cursor: Optional[str] = None

        for instr in instructions:
            if instr.get("type") != "TimelineAddEntries":
                continue
            for entry in instr.get("entries", []):
                content = entry.get("content", {})

                # ---- 游标条目（翻页用） ----
                if content.get("entryType") == "TimelineTimelineCursor":
                    if content.get("cursorType") == "Bottom":
                        next_cursor = content.get("value")
                    continue

                # ---- 推文条目 ----
                if content.get("entryType") != "TimelineTimelineItem":
                    continue

                tweet_result = (
                    content.get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                if not tweet_result:
                    continue

                # 解包被隐藏的推文
                if tweet_result.get("__typename") == "TweetWithVisibilityResults":
                    tweet_result = tweet_result.get("tweet", {})

                legacy = tweet_result.get("legacy", {})
                if not legacy:
                    continue

                # ---- 过滤转推 ----
                if legacy.get("full_text", "").startswith("RT @"):
                    continue

                # ---- 过滤回复 ----
                in_reply_to = legacy.get("in_reply_to_status_id_str")
                # 注意：有些推文同时包含文字和引用，不算纯回复
                # 只有当它是回复且没有原创内容时才跳过
                if in_reply_to and not _has_original_content(legacy):
                    continue

                # ---- 文本 ----
                text = legacy.get("full_text", "")
                # 如果有 note_tweet（长文），用它的文本替代
                note_text = (
                    tweet_result.get("note_tweet", {})
                    .get("note_tweet_results", {})
                    .get("result", {})
                    .get("text", "")
                )
                if note_text:
                    text = note_text

                if not text.strip():
                    continue

                # ---- 推文 ID ----
                tid = tweet_result.get("rest_id", "")
                if not tid:
                    continue

                # ---- 时间 ----
                created_at: Optional[datetime] = None
                created_str = legacy.get("created_at", "")
                try:
                    created_at = datetime.strptime(
                        created_str, "%a %b %d %H:%M:%S %z %Y"
                    )
                except (ValueError, TypeError):
                    pass

                # ---- 图片 ----
                images: List[str] = []
                seen = set()
                for source in [
                    legacy.get("entities", {}).get("media", []),
                    legacy.get("extended_entities", {}).get("media", []),
                ]:
                    for media in source:
                        if media.get("type") != "photo":
                            continue
                        img_url = media.get("media_url_https", "")
                        if img_url:
                            clean = img_url.split("?")[0] + "?format=jpg&name=large"
                            if clean not in seen:
                                seen.add(clean)
                                images.append(clean)

                # ---- 链接 ----
                url = f"https://x.com/{username}/status/{tid}"

                results.append({
                    "id": tid,
                    "text": text.strip(),
                    "created_at": created_at or datetime.utcnow(),
                    "url": url,
                    "images": images,
                })

                if len(results) >= count:
                    return results, next_cursor

        return results, next_cursor

    # ------------------------------------------------------------------
    #  GraphQL 请求 + 解析
    # ------------------------------------------------------------------

    def _fetch_timeline(
        self,
        query_id: str,
        operation_name: str,
        user_id: str,
        username: str,
        count: int = 25,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        调用 GraphQL API 并解析返回的 timeline。

        Returns
        -------
        (tweets_list, next_cursor)
        """
        variables: dict = {
            "userId": user_id,
            "count": min(count + 10, 50),
            "includePromotedContent": False,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }
        if cursor:
            variables["cursor"] = cursor
        if "SuperFollow" in operation_name:
            variables["withSuperFollowsUserFields"] = True

        features = json.dumps({
            "responsive_web_graphql_exclude_directive_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
        })

        resp = self.session.get(
            f"https://x.com/i/api/graphql/{query_id}/{operation_name}",
            params={"variables": json.dumps(variables), "features": features},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()

        instructions = (
            data.get("data", {})
            .get("user", {})
            .get("result", {})
            .get("timeline", {})
            .get("timeline", {})
            .get("instructions", [])
        )

        return self._parse_timeline_instructions(instructions, username, count)

    # ------------------------------------------------------------------
    #  公开方法
    # ------------------------------------------------------------------

    def fetch_tweets_with_cursor(
        self,
        username: str,
        count: int = 25,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        获取用户最近推文，支持游标翻页。

        Returns
        -------
        (tweets_list, next_cursor)
            tweets_list: 每条包含 id, text, created_at, url, images
            next_cursor:  下一页游标，None 表示没有更多推文
        """
        self._refresh_query_ids()
        user_id = self._get_user_id(username)
        return self._fetch_timeline(
            query_id=self._user_tweets_qid,  # type: ignore[arg-type]
            operation_name="UserTweets",
            user_id=user_id,
            username=username,
            count=count,
            cursor=cursor,
        )

    def get_recent_tweets(
        self, username: str, count: int = 25
    ) -> List[Dict[str, Any]]:
        """
        获取用户最近推文（不含转推和回复）。

        Returns
        -------
        list[dict]  每项: id, text, created_at, url, images
        失败时返回空列表。
        """
        try:
            tweets, _ = self.fetch_tweets_with_cursor(
                username=username, count=count, cursor=None
            )
            return tweets
        except Exception as exc:
            print(f"❌ X 采集失败: {exc}")
            import traceback
            traceback.print_exc()
            return []

    def get_super_follow_tweets(
        self,
        username: str,
        count: int = 100,
        cursor: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        获取付费订阅专属推文（UserSuperFollowTweets）。

        需要认证账号已付费订阅该用户，否则返回空列表。

        Returns
        -------
        (tweets_list, next_cursor)
        """
        self._refresh_query_ids()

        # 优先使用自动提取的 queryId，否则使用备用值
        qid = self._super_follow_tweets_qid or FALLBACK_SUPER_FOLLOW_QID
        user_id = self._get_user_id(username)

        return self._fetch_timeline(
            query_id=qid,
            operation_name="UserSuperFollowTweets",
            user_id=user_id,
            username=username,
            count=count,
            cursor=cursor,
        )


# ------------------------------------------------------------------
def _has_original_content(legacy: dict) -> bool:
    """判断推文是否有原创内容（不只是回复）。"""
    # 如果有 media，算有原创内容
    if legacy.get("entities", {}).get("media"):
        return True
    if legacy.get("extended_entities", {}).get("media"):
        return True
    # 如果有链接或引用，也算
    if legacy.get("entities", {}).get("urls"):
        return True
    # 如果全文和显示的文本长度不同（被截断），说明有内容
    full = legacy.get("full_text", "")
    display = legacy.get("display_text_range", [0, len(full)])
    if display[-1] > 50:  # 超过 50 字符的回复算有内容
        return True
    return False
