"""
Google Sheets writer.
Appends post data to a Google Sheet using a Service Account.
Only writes rows whose short_code doesn't already exist in the sheet.
"""
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import gspread
from gspread.exceptions import APIError

from scraper.csv_writer import POSTS_COLUMNS

HIGHLIGHTS_COLUMNS = ["highlight_id", "item_id", "taken_at", "image_url", "is_video", "ocr_text"]

CREDENTIALS_PATH = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", ""))

# Seconds to sleep between batch writes to avoid hitting Sheets API rate limits
WRITE_SLEEP = 1.2


def _get_client() -> gspread.Client:
    return gspread.service_account(filename=str(CREDENTIALS_PATH))


def get_or_create_worksheet(spreadsheet_id: str, username: str) -> gspread.Worksheet:
    """Returns the worksheet named after the username, creating it if needed."""
    gc = _get_client()
    sh = gc.open_by_key(spreadsheet_id)

    try:
        ws = sh.worksheet(username)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=username, rows=5000, cols=len(POSTS_COLUMNS))
        # Write header row
        ws.append_row(POSTS_COLUMNS, value_input_option="RAW")
        time.sleep(WRITE_SLEEP)

    return ws


def get_existing_short_codes(ws: gspread.Worksheet) -> set[str]:
    """Returns the set of short_codes already in the worksheet."""
    try:
        all_values = ws.get_all_values()
    except APIError:
        return set()

    if len(all_values) < 2:
        return set()

    header = all_values[0]
    if "short_code" not in header:
        return set()

    col_index = header.index("short_code")
    return {row[col_index] for row in all_values[1:] if len(row) > col_index and row[col_index]}


def fetch_existing_short_codes(spreadsheet_id: str, username: str) -> set[str]:
    """
    Reads the sheet and returns the set of short_codes already present for this username.
    Returns an empty set on any error (missing sheet, auth failure, etc.).
    """
    try:
        gc = _get_client()
        sh = gc.open_by_key(spreadsheet_id)
        ws = sh.worksheet(username)
        return get_existing_short_codes(ws)
    except Exception:
        return set()


def write_posts_to_sheet(
    posts: list[dict],
    spreadsheet_id: str,
    username: str,
    progress_callback: Optional[Callable] = None,
) -> int:
    """
    Appends only new posts (not already in the sheet) to the worksheet.
    Returns the number of rows actually written.
    """
    def notify(msg: str):
        if progress_callback:
            progress_callback(msg)

    if not posts:
        return 0

    notify(f"連接 Google Sheets...")
    ws = get_or_create_worksheet(spreadsheet_id, username)

    notify("檢查已存在的資料...")
    existing = get_existing_short_codes(ws)
    notify(f"Sheet 上已有 {len(existing)} 筆資料")

    new_posts = [p for p in posts if p.get("short_code") not in existing]
    if not new_posts:
        notify("所有貼文已是最新，無需新增。")
        return 0

    notify(f"準備新增 {len(new_posts)} 筆新貼文...")

    # Write in batches of 50 to avoid payload limits
    batch_size = 50
    written = 0
    for i in range(0, len(new_posts), batch_size):
        batch = new_posts[i : i + batch_size]
        rows = [[str(p.get(col, "")) for col in POSTS_COLUMNS] for p in batch]
        ws.append_rows(rows, value_input_option="RAW")
        written += len(batch)
        notify(f"Google Sheets 寫入進度：{written}/{len(new_posts)}")
        time.sleep(WRITE_SLEEP)

    notify(f"Google Sheets 完成，新增了 {written} 筆貼文。")
    return written


def _sanitize_sheet_name(name: str) -> str:
    """Removes characters not allowed in Google Sheets tab names and trims to 100 chars."""
    import re as _re
    sanitized = _re.sub(r'[\\/*?\[\]:]', '', name).strip()
    return sanitized[:100] if sanitized else "highlights"


def write_highlights_to_sheet(
    highlight_id: str,
    title: str,
    items: list[dict],
    spreadsheet_id: str,
    progress_callback: Optional[Callable] = None,
) -> int:
    """
    Writes highlight OCR results to a worksheet named after the highlight title.
    Skips item_ids that already exist in the sheet.
    Returns the number of rows written.
    """
    def notify(msg: str) -> None:
        if progress_callback:
            progress_callback(msg)

    if not items:
        return 0

    tab_name = _sanitize_sheet_name(title)
    notify(f"連接 Google Sheets（分頁：{tab_name}）...")

    gc = _get_client()
    sh = gc.open_by_key(spreadsheet_id)

    try:
        ws = sh.worksheet(tab_name)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=tab_name, rows=5000, cols=len(HIGHLIGHTS_COLUMNS))
        ws.append_row(HIGHLIGHTS_COLUMNS, value_input_option="RAW")
        time.sleep(WRITE_SLEEP)

    # Avoid duplicates by checking existing item_ids
    existing_ids: set[str] = set()
    try:
        all_values = ws.get_all_values()
        if len(all_values) >= 2:
            header = all_values[0]
            if "item_id" in header:
                col_idx = header.index("item_id")
                existing_ids = {
                    row[col_idx]
                    for row in all_values[1:]
                    if len(row) > col_idx and row[col_idx]
                }
    except APIError:
        pass

    new_items = [it for it in items if it.get("item_id") not in existing_ids]
    if not new_items:
        notify("所有資料已是最新，無需新增。")
        return 0

    notify(f"準備新增 {len(new_items)} 筆資料...")

    batch_size = 50
    written = 0
    for i in range(0, len(new_items), batch_size):
        batch = new_items[i : i + batch_size]
        rows = []
        for it in batch:
            taken_at_ts = it.get("taken_at", 0)
            taken_at_str = (
                datetime.fromtimestamp(taken_at_ts).strftime("%Y-%m-%d %H:%M:%S")
                if taken_at_ts
                else ""
            )
            rows.append([
                highlight_id,
                str(it.get("item_id", "")),
                taken_at_str,
                str(it.get("image_url", "")),
                "是" if it.get("is_video") else "否",
                str(it.get("ocr_text", "")),
            ])
        ws.append_rows(rows, value_input_option="RAW")
        written += len(batch)
        notify(f"Google Sheets 寫入進度：{written}/{len(new_items)}")
        time.sleep(WRITE_SLEEP)

    notify(f"Google Sheets 完成，新增了 {written} 筆資料。")
    return written
