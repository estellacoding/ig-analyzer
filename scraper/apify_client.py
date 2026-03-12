"""
Apify API wrapper.
Handles Instagram post scraping and comment scraping via two separate Apify actors.
"""
from datetime import datetime
from typing import Callable, Optional

from apify_client import ApifyClient

POSTS_ACTOR = "apify/instagram-scraper"
COMMENTS_ACTOR = "apify/instagram-comment-scraper"


def run_instagram_scrape(
    profile_url: str,
    api_token: str,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """
    Runs Apify instagram-scraper for all posts on a public profile.
    Returns a list of normalized post dicts.
    """
    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    notify("Connecting to Apify...")
    client = ApifyClient(api_token)

    run_input = {
        "directUrls": [profile_url],
        "resultsType": "posts",
        "resultsLimit": 99999,
    }

    notify("Apify actor running... (may take 2-10 mins for large profiles)")

    try:
        run = client.actor(POSTS_ACTOR).call(run_input=run_input, timeout_secs=600)
    except Exception as e:
        raise RuntimeError(f"Apify posts actor failed: {e}")

    if run is None:
        raise RuntimeError("Apify returned no result. Check your API token.")

    notify(f"Reading results from dataset...")
    raw_items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    notify(f"Retrieved {len(raw_items)} posts from Apify.")

    posts = []
    for i, item in enumerate(raw_items):
        try:
            posts.append(_normalize_post(item, post_number=i + 1))
        except Exception as e:
            notify(f"Warning: skipped post {i+1}: {e}")

    return posts


def run_single_post_scrape(
    post_url: str,
    api_token: str,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """
    Scrapes a single Instagram post URL.
    Returns a one-item list with the normalized post dict.
    """
    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    notify("Connecting to Apify (single post)...")
    client = ApifyClient(api_token)

    run_input = {
        "directUrls": [post_url],
        "resultsType": "posts",
        "resultsLimit": 1,
    }

    notify("Fetching post data...")

    try:
        run = client.actor(POSTS_ACTOR).call(run_input=run_input, timeout_secs=120)
    except Exception as e:
        raise RuntimeError(f"Apify actor failed: {e}")

    if run is None:
        raise RuntimeError("Apify returned no result. Check your API token.")

    raw_items = list(client.dataset(run["defaultDatasetId"]).iterate_items())

    posts = []
    for i, item in enumerate(raw_items):
        try:
            posts.append(_normalize_post(item, post_number=i + 1))
        except Exception as e:
            notify(f"Warning: could not parse post: {e}")

    return posts


def run_comments_scrape(
    post_urls: list[str],
    api_token: str,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    """
    Runs Apify instagram-comment-scraper for a list of post URLs.
    Returns a flat list of normalized comment dicts (all posts combined).
    """
    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    if not post_urls:
        return []

    notify(f"Fetching comments for {len(post_urls)} posts via Apify...")
    notify("(This may take a long time for profiles with many comments)")

    client = ApifyClient(api_token)

    run_input = {
        "directUrls": post_urls,
        "resultsLimit": 99999,
    }

    try:
        run = client.actor(COMMENTS_ACTOR).call(run_input=run_input, timeout_secs=1200)
    except Exception as e:
        raise RuntimeError(f"Apify comments actor failed: {e}")

    if run is None:
        raise RuntimeError("Apify comments actor returned no result.")

    notify("Reading comment results...")
    raw_items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
    notify(f"Retrieved {len(raw_items)} total comments.")

    comments = []
    comment_counters: dict[str, int] = {}

    for item in raw_items:
        try:
            normalized = _normalize_comment(item, comment_counters)
            if normalized:
                comments.append(normalized)
        except Exception as e:
            notify(f"Warning: skipped a comment: {e}")

    return comments


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_timestamp(ts: str) -> tuple[str, str]:
    """Returns (date_str, time_str) from an ISO 8601 timestamp, or ('', '')."""
    if not ts:
        return "", ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
    except ValueError:
        return ts[:10] if len(ts) >= 10 else "", ""


def _normalize_post(raw: dict, post_number: int) -> dict:
    """Converts a raw Apify post item into a clean flat dict."""
    date_str, time_str = _parse_timestamp(raw.get("timestamp", ""))

    likes_raw = raw.get("likesCount", 0)
    likes = "" if likes_raw == -1 else (likes_raw or 0)

    caption = (raw.get("caption") or "").replace("\n", " | ").replace("\r", "")

    hashtags = raw.get("hashtags", []) or []
    hashtags_str = ", ".join(f"#{tag}" for tag in hashtags)

    display_url = raw.get("displayUrl", "")
    child_posts = raw.get("childPosts", []) or []
    all_image_urls = [display_url] + [
        c.get("displayUrl", "") for c in child_posts if c.get("displayUrl")
    ]

    post_type_raw = raw.get("__typename", raw.get("type", "Image"))
    if "Sidecar" in str(post_type_raw) or len(child_posts) > 0:
        post_type = "Carousel"
    elif "Video" in str(post_type_raw):
        post_type = "Video"
    else:
        post_type = "Image"

    return {
        "post_number": post_number,
        "date": date_str,
        "time": time_str,
        "post_url": raw.get("url", ""),
        "post_type": post_type,
        "caption": caption,
        "hashtags": hashtags_str,
        "likes_count": likes,
        "comments_count": raw.get("commentsCount", 0) or 0,
        "image_url_1": all_image_urls[0] if len(all_image_urls) > 0 else "",
        "image_url_2": all_image_urls[1] if len(all_image_urls) > 1 else "",
        "image_url_3": all_image_urls[2] if len(all_image_urls) > 2 else "",
        "short_code": raw.get("shortCode", ""),
        "owner_username": raw.get("ownerUsername", ""),
        # Private fields used by image downloader (not written to CSV)
        "_all_image_urls": all_image_urls,
        "_video_url": raw.get("videoUrl", ""),
    }


def _normalize_comment(raw: dict, counters: dict) -> Optional[dict]:
    """Converts a raw Apify comment item into a clean flat dict."""
    # The comment scraper returns the post URL in 'postUrl' or 'url'
    post_url = raw.get("postUrl") or raw.get("url", "")

    # Extract short_code from post URL  e.g. .../p/ABC123/
    short_code = ""
    if "/p/" in post_url:
        short_code = post_url.rstrip("/").split("/p/")[-1].split("/")[0]

    if not short_code:
        return None

    counters[short_code] = counters.get(short_code, 0) + 1

    ts = raw.get("timestamp") or raw.get("createdAt", "")
    date_str, time_str = _parse_timestamp(ts)
    comment_datetime = f"{date_str} {time_str}".strip() if date_str else ""

    text = (raw.get("text") or raw.get("comment", "")).replace("\n", " ").replace("\r", "")
    commenter = raw.get("ownerUsername") or raw.get("username", "")

    return {
        "short_code": short_code,
        "post_url": post_url,
        "comment_number": counters[short_code],
        "commenter": commenter,
        "comment_text": text,
        "comment_date": comment_datetime,
        "comment_likes": raw.get("likesCount", 0) or 0,
    }
