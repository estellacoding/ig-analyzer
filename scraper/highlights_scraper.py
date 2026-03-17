"""
Highlights scraper using Instagram's internal web API.
Fetches all items (images/videos) from an Instagram Highlight reel.
No login required for public accounts.
"""
import re
import requests
from typing import Callable, Optional

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "X-IG-App-ID": "936619743392459",
    "Accept": "*/*",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.instagram.com/",
    "Origin": "https://www.instagram.com",
}


def extract_highlight_id(url: str) -> str:
    """Parses the numeric highlight ID from a URL like:
    https://www.instagram.com/stories/highlights/18309799063249347/
    """
    match = re.search(r"/highlights/(\d+)", url)
    if not match:
        raise ValueError(f"無法從 URL 解析 Highlight ID：{url}")
    return match.group(1)


def fetch_highlight_items(
    highlight_id: str,
    session_id: str = "",
    progress_callback: Optional[Callable] = None,
) -> tuple[str, list[dict]]:
    """
    Calls Instagram's internal reels_media API.
    Returns (title, items) where:
      title   – highlight reel title (e.g. "旅遊")
      items   – list of dicts with keys:
                  item_id, taken_at, image_url, video_url, is_video

    session_id: Instagram sessionid cookie value (required for most highlights).
    """
    def notify(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    api_url = (
        "https://www.instagram.com/api/v1/feed/reels_media/"
        f"?reel_ids=highlight:{highlight_id}"
    )
    notify("連接 Instagram Highlights API...")

    session = requests.Session()
    session.headers.update(_HEADERS)
    if session_id:
        session.cookies.set("sessionid", session_id, domain=".instagram.com")

    try:
        resp = session.get(api_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"無法連接 Instagram API：{exc}")
    except ValueError:
        raise RuntimeError("Instagram API 回傳格式錯誤，請確認 Highlights URL 是否正確。")

    reels = data.get("reels_media", [])
    if not reels:
        hint = "（提示：請確認 Session ID 是否正確，或重新從瀏覽器複製。）" if session_id else "（提示：此 API 需要登入，請填入 Instagram Session ID。）"
        raise RuntimeError(f"找不到 Highlight 資料。該 Highlight 可能已刪除或為私人帳號。{hint}")

    reel = reels[0]
    title = reel.get("title", "").strip() or f"highlights_{highlight_id}"

    items_raw = reel.get("items", [])
    if not items_raw:
        raise RuntimeError("此 Highlight 沒有任何內容。")

    notify(f"找到「{title}」，共 {len(items_raw)} 個項目，開始處理...")

    items = []
    for raw in items_raw:
        is_video = raw.get("media_type") == 2

        # Best image (first candidate = highest resolution)
        image_url = ""
        candidates = raw.get("image_versions2", {}).get("candidates", [])
        if candidates:
            image_url = candidates[0].get("url", "")

        # Video URL (only relevant when is_video)
        video_url = ""
        if is_video:
            video_versions = raw.get("video_versions", [])
            if video_versions:
                video_url = video_versions[0].get("url", "")

        items.append({
            "item_id": str(raw.get("pk", "")),
            "taken_at": raw.get("taken_at", 0),
            "image_url": image_url,
            "video_url": video_url,
            "is_video": is_video,
        })

    return title, items
