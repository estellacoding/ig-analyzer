"""
CSV generation.
Writes posts.csv for Google Sheets import.
"""
import csv
from pathlib import Path

POSTS_COLUMNS = [
    "short_code",
    "date",
    "time",
    "post_type",
    "caption",
    "hashtags",
    "likes_count",
    "comments_count",
    "post_url",
    "image_url_1",
    "image_url_2",
    "image_url_3",
    "image_text",
]


def write_posts_csv(posts: list[dict], output_path: Path) -> None:
    """Writes posts data to a UTF-8 CSV file (BOM for Excel/Sheets compatibility)."""
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=POSTS_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for post in posts:
            writer.writerow({col: post.get(col, "") for col in POSTS_COLUMNS})
