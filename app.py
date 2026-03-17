"""
Instagram Social Analyzer
Flask web application — main entry point.

Run with:
    source venv/bin/activate
    python app.py

Then open: http://localhost:8080
"""
import json
import os
import queue
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request, send_file

load_dotenv()

from scraper.instaloader_client import run_instagram_scrape, run_single_post_scrape
from scraper.csv_writer import write_posts_csv
from scraper.image_downloader import download_all_posts, _download_one
from scraper.ocr import extract_text_for_post, extract_text
from scraper.sheets_writer import write_posts_to_sheet, fetch_existing_short_codes, write_highlights_to_sheet
from scraper.highlights_scraper import extract_highlight_id, fetch_highlight_items

app = Flask(__name__)

DOWNLOADS_DIR = Path(__file__).parent / "downloads"

jobs: dict = {}
jobs_lock = threading.Lock()


def _parse_date(s: str) -> Optional[date]:
    """Parses a YYYY-MM-DD string into a date, returns None if empty/invalid."""
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _background_job(job_id: str, profile_url: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> None:
    q = jobs[job_id]["queue"]

    def notify(message: str, status: str = "progress") -> None:
        q.put(json.dumps({"status": status, "message": message}))

    try:
        clean_url = profile_url.rstrip("/").split("?")[0]
        username = clean_url.split("/")[-1] or "profile"

        output_dir = DOWNLOADS_DIR / username
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        posts = run_instagram_scrape(
            profile_url=profile_url,
            start_date=start_date,
            end_date=end_date,
            progress_callback=notify,
        )

        if not posts:
            notify("找不到貼文，請確認帳號是否為公開。", status="error")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        # Check Google Sheets for already-existing posts before downloading
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
        existing_short_codes: set = set()
        if sheet_id:
            notify("檢查 Google Sheets 現有資料...")
            existing_short_codes = fetch_existing_short_codes(sheet_id, username)
            if existing_short_codes:
                notify(f"Google Sheets 已有 {len(existing_short_codes)} 筆，篩選新貼文中...")

        new_posts = [p for p in posts if p.get("short_code") not in existing_short_codes]

        if not new_posts:
            notify(f"篩選範圍內的 {len(posts)} 篇貼文皆已在 Google Sheets，無需更新。", status="done")
            with jobs_lock:
                jobs[job_id]["status"] = "done"
                jobs[job_id]["csv_path"] = None
            return

        if existing_short_codes:
            notify(f"共 {len(new_posts)} 篇新貼文（跳過 {len(posts) - len(new_posts)} 篇已有），下載圖片中...")
        else:
            notify(f"共 {len(new_posts)} 篇貼文，下載圖片中...")

        download_all_posts(new_posts, images_dir, progress_callback=notify)

        notify("圖片文字辨識中（第一次需下載模型，請稍候）...")
        for i, post in enumerate(new_posts):
            post["image_text"] = extract_text_for_post(
                short_code=post.get("short_code", ""),
                date_str=post.get("date", ""),
                post_type=post.get("post_type", "Image"),
                images_dir=images_dir,
            )
            if (i + 1) % 10 == 0 or i == len(new_posts) - 1:
                notify(f"OCR 進度：{i + 1}/{len(new_posts)}")

        posts_csv = output_dir / "posts.csv"
        write_posts_csv(new_posts, posts_csv)
        notify("CSV 已寫入。")

        if sheet_id:
            write_posts_to_sheet(new_posts, sheet_id, username, progress_callback=notify)
        else:
            notify("未設定 GOOGLE_SHEET_ID，跳過 Google Sheets 同步。")

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["csv_path"] = str(posts_csv)

        notify(f"完成！新增 {len(new_posts)} 篇貼文，已存到 downloads/{username}/", status="done")

    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
        notify(f"錯誤：{exc}", status="error")


def _background_single(job_id: str, post_url: str) -> None:
    q = jobs[job_id]["queue"]

    def notify(message: str, status: str = "progress") -> None:
        q.put(json.dumps({"status": status, "message": message}))

    try:
        short_code = post_url.rstrip("/").split("/p/")[-1].split("/")[0] if "/p/" in post_url else "single_post"

        output_dir = DOWNLOADS_DIR / short_code
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        posts = run_single_post_scrape(post_url=post_url, progress_callback=notify)

        if not posts:
            notify("無法取得貼文資料，請確認連結。", status="error")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        # Check if this post already exists in Google Sheets
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
        username = posts[0].get("owner_username", short_code)
        if sheet_id:
            existing = fetch_existing_short_codes(sheet_id, username)
            if short_code in existing:
                notify(f"此貼文已在 Google Sheets 中，無需更新。", status="done")
                with jobs_lock:
                    jobs[job_id]["status"] = "done"
                    jobs[job_id]["csv_path"] = None
                return

        notify("下載圖片中...")
        download_all_posts(posts, images_dir, progress_callback=notify)

        notify("圖片文字辨識中...")
        posts[0]["image_text"] = extract_text_for_post(
            short_code=posts[0].get("short_code", ""),
            date_str=posts[0].get("date", ""),
            post_type=posts[0].get("post_type", "Image"),
            images_dir=images_dir,
        )

        posts_csv = output_dir / "posts.csv"
        write_posts_csv(posts, posts_csv)
        notify("CSV 已寫入。")

        if sheet_id:
            write_posts_to_sheet(posts, sheet_id, username, progress_callback=notify)
        else:
            notify("未設定 GOOGLE_SHEET_ID，跳過 Google Sheets 同步。")

        with jobs_lock:
            jobs[job_id]["status"] = "done"
            jobs[job_id]["csv_path"] = str(posts_csv)

        notify(f"完成！貼文資料已存到 downloads/{short_code}/", status="done")

    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
        notify(f"錯誤：{exc}", status="error")


def _background_highlights(job_id: str, highlight_url: str, session_id: str = "") -> None:
    q = jobs[job_id]["queue"]

    def notify(message: str, status: str = "progress") -> None:
        q.put(json.dumps({"status": status, "message": message}))

    try:
        highlight_id = extract_highlight_id(highlight_url)
        notify(f"Highlight ID：{highlight_id}")

        output_dir = DOWNLOADS_DIR / f"highlights_{highlight_id}"
        images_dir = output_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)

        title, items = fetch_highlight_items(highlight_id, session_id=session_id, progress_callback=notify)

        if not items:
            notify("找不到任何 Highlight 項目。", status="error")
            with jobs_lock:
                jobs[job_id]["status"] = "error"
            return

        # Download images (use thumbnail for videos)
        notify(f"下載 {len(items)} 張圖片中...")
        fail_count = 0
        for i, item in enumerate(items):
            url = item["image_url"]
            filename = f"{item['item_id']}.jpg"
            save_path = images_dir / filename
            item["_local_path"] = save_path

            if url:
                ok = _download_one(url, save_path)
                if not ok:
                    fail_count += 1

            if (i + 1) % 10 == 0 or i == len(items) - 1:
                notify(
                    f"下載進度：{i + 1}/{len(items)}"
                    + (f"（{fail_count} 失敗）" if fail_count else "")
                )

        # OCR — skip video items (only thumbnail downloaded, no meaningful text)
        notify("圖片文字辨識中...")
        for i, item in enumerate(items):
            local_path = item.get("_local_path")
            if local_path and not item["is_video"] and local_path.exists():
                item["ocr_text"] = extract_text(local_path)
            else:
                item["ocr_text"] = ""

            if (i + 1) % 10 == 0 or i == len(items) - 1:
                notify(f"OCR 進度：{i + 1}/{len(items)}")

        # Write to Google Sheets
        sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
        if sheet_id:
            write_highlights_to_sheet(highlight_id, title, items, sheet_id, progress_callback=notify)
        else:
            notify("未設定 GOOGLE_SHEET_ID，跳過 Google Sheets 同步。")

        with jobs_lock:
            jobs[job_id]["status"] = "done"

        notify(
            f"完成！{len(items)} 個項目已存入 Google Sheets（分頁：{title}）",
            status="done",
        )

    except Exception as exc:
        with jobs_lock:
            jobs[job_id]["status"] = "error"
        notify(f"錯誤：{exc}", status="error")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start_job():
    data = request.get_json() or {}
    profile_url = data.get("profile_url", "").strip()

    if not profile_url or "instagram.com/" not in profile_url:
        return jsonify({"error": "請輸入有效的 Instagram 主頁連結。"}), 400

    start_date = _parse_date(data.get("start_date", ""))
    end_date = _parse_date(data.get("end_date", ""))

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {"queue": queue.Queue(), "status": "running", "csv_path": None}

    threading.Thread(target=_background_job, args=(job_id, profile_url, start_date, end_date), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/start-single", methods=["POST"])
def start_single_job():
    data = request.get_json() or {}
    post_url = data.get("post_url", "").strip()

    if not post_url or "instagram.com/p/" not in post_url:
        return jsonify({"error": "請輸入有效的 Instagram 貼文連結（需包含 /p/）。"}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {"queue": queue.Queue(), "status": "running", "csv_path": None}

    threading.Thread(target=_background_single, args=(job_id, post_url), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/start-highlights", methods=["POST"])
def start_highlights_job():
    data = request.get_json() or {}
    highlight_url = data.get("highlight_url", "").strip()
    session_id = data.get("session_id", "").strip()

    if not highlight_url or "instagram.com/stories/highlights/" not in highlight_url:
        return jsonify({"error": "請輸入有效的 Instagram Highlights 連結。"}), 400

    job_id = str(uuid.uuid4())
    with jobs_lock:
        jobs[job_id] = {"queue": queue.Queue(), "status": "running", "csv_path": None}

    threading.Thread(target=_background_highlights, args=(job_id, highlight_url, session_id), daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/progress/<job_id>")
def progress(job_id: str):
    if job_id not in jobs:
        return jsonify({"error": "Job not found"}), 404

    def generate():
        q = jobs[job_id]["queue"]
        while True:
            try:
                msg = q.get(timeout=25)
                yield f"data: {msg}\n\n"
                if json.loads(msg).get("status") in ("done", "error"):
                    break
            except queue.Empty:
                yield 'data: {"status": "heartbeat"}\n\n'

    return Response(generate(), mimetype="text/event-stream",
                    headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})


@app.route("/download/<job_id>")
def download_csv(job_id: str):
    with jobs_lock:
        job = jobs.get(job_id, {})

    if job.get("status") != "done" or not job.get("csv_path"):
        return jsonify({"error": "File not ready"}), 404

    csv_path = Path(job["csv_path"])
    if not csv_path.exists():
        return jsonify({"error": "File not found on disk"}), 404

    return send_file(csv_path, as_attachment=True, download_name=csv_path.name)


if __name__ == "__main__":
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    port = int(os.getenv("PORT", "8080"))
    print(f"\n Instagram Analyzer is running!")
    print(f" Open your browser to: http://localhost:{port}\n")
    app.run(debug=False, host="127.0.0.1", port=port, threaded=True)
