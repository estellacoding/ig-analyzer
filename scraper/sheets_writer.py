"""
Google Sheets writer.
Appends post data to a Google Sheet using a Service Account.
Only writes rows whose short_code doesn't already exist in the sheet.
"""
import os
import time
from pathlib import Path
from typing import Callable, Optional

import gspread
from gspread.exceptions import APIError

from scraper.csv_writer import POSTS_COLUMNS

_creds_env = os.getenv("GOOGLE_CREDENTIALS_PATH", "").strip()
CREDENTIALS_PATH = Path(_creds_env) if _creds_env else Path(__file__).parent.parent / "credentials" / "social-analyzer-490003-8e9b302db91d.json"

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
