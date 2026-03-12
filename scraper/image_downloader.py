"""
Downloads images and videos from CDN URLs.
Files are saved to the profile's images/ subdirectory.
"""
import requests
from pathlib import Path
from typing import Callable, Optional

_HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def _download_one(url: str, save_path: Path) -> bool:
    """Downloads a single file. Returns True on success. Idempotent (skips if exists)."""
    if not url:
        return False
    if save_path.exists() and save_path.stat().st_size > 0:
        return True

    try:
        response = requests.get(url, stream=True, timeout=30, headers=_HEADERS)
        response.raise_for_status()
        with open(save_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        return True
    except requests.RequestException:
        return False


def download_all_posts(
    posts: list[dict],
    images_dir: Path,
    progress_callback: Optional[Callable] = None,
) -> None:
    """
    Downloads all images/videos for a list of normalized post dicts.
    Reports progress every 10 items.
    """
    total = len(posts)
    fail_count = 0

    for i, post in enumerate(posts):
        date_str = post.get("date", "unknown")
        short_code = post.get("short_code", f"post{i}")
        post_type = post.get("post_type", "Image")

        if post_type == "Video":
            video_url = post.get("_video_url") or post.get("image_url_1", "")
            filename = f"{date_str}_{short_code}.mp4"
            ok = _download_one(video_url, images_dir / filename)

        elif post_type == "Carousel":
            all_urls = post.get("_all_image_urls", [])
            ok = False
            for j, url in enumerate(all_urls, start=1):
                filename = f"{date_str}_{short_code}_slide{j}.jpg"
                slide_ok = _download_one(url, images_dir / filename)
                ok = ok or slide_ok

        else:  # Image
            image_url = post.get("image_url_1", "")
            filename = f"{date_str}_{short_code}.jpg"
            ok = _download_one(image_url, images_dir / filename)

        if not ok:
            fail_count += 1

        if progress_callback and (i % 10 == 0 or i == total - 1):
            progress_callback(
                f"Downloading media... {i + 1}/{total}"
                + (f" ({fail_count} failed)" if fail_count else "")
            )
