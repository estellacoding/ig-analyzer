"""
Instagram scraper using instaloader (no login required).
Works on public profiles only.
"""
import instaloader
from datetime import date
from typing import Callable, Optional


def _make_loader() -> instaloader.Instaloader:
    return instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )


def run_instagram_scrape(
    profile_url: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    username = profile_url.rstrip("/").split("?")[0].rstrip("/").split("/")[-1]
    notify(f"載入帳號 @{username} ...")

    L = _make_loader()

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except instaloader.exceptions.ProfileNotExistsException:
        raise RuntimeError(f"找不到帳號 @{username}，請確認 URL 或該帳號是否為公開。")

    total = profile.mediacount
    date_hint = ""
    if start_date or end_date:
        s = start_date.isoformat() if start_date else "最早"
        e = end_date.isoformat() if end_date else "最新"
        date_hint = f"（僅篩選：{s} ～ {e}）"
    notify(f"找到 @{username}，共 {total} 篇貼文，開始抓取... {date_hint}")

    posts = []
    checked = 0
    for post in profile.get_posts():
        post_date = post.date_utc.date()
        checked += 1

        # Posts are in reverse chronological order (newest first)
        if end_date and post_date > end_date:
            continue
        if start_date and post_date < start_date:
            break  # All remaining posts are older, stop early

        posts.append(_normalize_post(post))

        if progress_callback and (checked % 10 == 0):
            notify(f"已掃描 {checked} 篇，符合條件 {len(posts)} 篇...")

    notify(f"篩選完成，共 {len(posts)} 篇貼文符合條件。")
    return posts


def run_single_post_scrape(
    post_url: str,
    progress_callback: Optional[Callable] = None,
) -> list[dict]:
    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    shortcode = post_url.rstrip("/").split("/p/")[-1].split("/")[0]
    notify(f"抓取貼文 {shortcode} ...")

    L = _make_loader()

    try:
        post = instaloader.Post.from_shortcode(L.context, shortcode)
    except Exception as e:
        raise RuntimeError(f"無法取得貼文資料：{e}")

    return [_normalize_post(post)]


def _normalize_post(post: instaloader.Post) -> dict:
    date_str = post.date_utc.strftime("%Y-%m-%d")
    time_str = post.date_utc.strftime("%H:%M:%S")

    caption = (post.caption or "").replace("\n", " | ").replace("\r", "")
    hashtags = ", ".join(f"#{tag}" for tag in (post.caption_hashtags or []))

    post_url = f"https://www.instagram.com/p/{post.shortcode}/"

    if post.typename == "GraphSidecar":
        post_type = "Carousel"
        all_image_urls = [node.display_url for node in post.get_sidecar_nodes()]
        video_url = ""
    elif post.typename == "GraphVideo":
        post_type = "Video"
        all_image_urls = [post.url]
        video_url = post.video_url
    else:
        post_type = "Image"
        all_image_urls = [post.url]
        video_url = ""

    return {
        "short_code": post.shortcode,
        "date": date_str,
        "time": time_str,
        "post_url": post_url,
        "post_type": post_type,
        "caption": caption,
        "hashtags": hashtags,
        "likes_count": post.likes,
        "comments_count": post.comments,
        "image_url_1": all_image_urls[0] if len(all_image_urls) > 0 else "",
        "image_url_2": all_image_urls[1] if len(all_image_urls) > 1 else "",
        "image_url_3": all_image_urls[2] if len(all_image_urls) > 2 else "",
        "owner_username": post.owner_username,
        "_all_image_urls": all_image_urls,
        "_video_url": video_url,
    }
