# Instagram Analyzer

抓取公開 IG 帳號貼文與精選動態資料、圖片文字辨識，自動同步至 Google Sheets。

## 功能

### 貼文分析
- 抓取公開 Instagram 帳號的所有貼文資料（不需登入）
- 支援篩選日期範圍，只抓取指定期間的貼文
- 支援單筆貼文抓取
- 自動下載貼文圖片與影片
- 使用 Apple Vision OCR 辨識圖片中的文字（支援繁體中文）
- 將結果匯出為 CSV（Excel 相容）
- 自動同步至 Google Sheets，具備增量更新機制（只新增未存在的貼文）

### 精選動態分析
- 抓取指定精選動態中的所有圖片
- 使用 Apple Vision OCR 辨識每張圖片的文字
- 自動同步至 Google Sheets，分頁以精選動態標題命名（如「旅遊」、「美食」）
- 需提供 Instagram Session ID（帳號本身不限公開或私人）

## 環境需求

- macOS（OCR 使用 Apple Vision，僅支援 macOS）
- Python 3.14+
- Conda

## 安裝

```bash
git clone https://github.com/estellacoding/ig-analyzer.git
cd ig-analyzer

conda create -n ig-analyzer python=3.14
conda activate ig-analyzer
pip install -r requirements.txt
```

## 設定

### 1. 環境變數

複製範本並填入設定：

```bash
cp .env.example .env
```

`.env` 內容：

```
GOOGLE_SHEET_ID=你的 Google Sheets 試算表 ID
GOOGLE_CREDENTIALS_PATH=credentials/你的金鑰檔名.json
```

試算表 ID 從網址取得：`https://docs.google.com/spreadsheets/d/[這段]/edit`

### 2. Google Sheets Service Account

1. 至 [Google Cloud Console](https://console.cloud.google.com/) 建立 Service Account
2. 下載 JSON 金鑰，放到 `credentials/` 資料夾
3. 在 `.env` 的 `GOOGLE_CREDENTIALS_PATH` 填入對應的檔名
4. 將 Service Account 的 email 加為 Google Sheet 的「編輯者」

## 使用方式

```bash
conda activate ig-analyzer
python app.py
```

開啟瀏覽器至 `http://localhost:8080`

---

### 貼文 Tab

#### 抓取主頁所有貼文

1. 貼上 Instagram 主頁 URL，例如 `https://www.instagram.com/yourusername`
2. 選填日期範圍（不填則抓全部）
3. 點擊「開始分析並存入 Sheets」

#### 抓取單筆貼文

1. 貼上單篇貼文 URL，例如 `https://www.instagram.com/p/ABC123/`
2. 點擊「分析單筆並存入 Sheets」

---

### 精選動態 Tab

#### 取得 Instagram Session ID

1. 瀏覽器開啟 [instagram.com](https://www.instagram.com) 並登入
2. 右鍵 → **檢查**（或 F12）→ **Application** → **Cookies** → `https://www.instagram.com`
3. 找到 `sessionid`，複製 Value 欄的值

#### 抓取精選動態

1. 貼上 Highlights URL，例如 `https://www.instagram.com/stories/highlights/18309799063249347/`
2. 貼上 Session ID
3. 點擊「開始分析並存入 Sheets」

---

## 輸出格式

### 貼文 — CSV 與 Google Sheets 欄位

| 欄位 | 說明 |
|------|------|
| short_code | 貼文短碼 |
| date | 發佈日期 |
| time | 發佈時間（UTC） |
| post_type | 類型（Image / Video / Carousel） |
| caption | 貼文文字 |
| hashtags | 標籤 |
| likes_count | 按讚數 |
| comments_count | 留言數 |
| post_url | 貼文連結 |
| image_url_1~3 | 圖片網址 |
| image_text | OCR 辨識出的圖片文字 |

Google Sheets 分頁名稱：帳號名稱（如 `yourusername`）

### 精選動態 — Google Sheets 欄位

| 欄位 | 說明 |
|------|------|
| highlight_id | Highlights 數字 ID |
| item_id | 單張圖片的媒體 ID |
| taken_at | 拍攝時間 |
| image_url | 圖片網址 |
| is_video | 是否為影片（是 / 否） |
| ocr_text | OCR 辨識出的圖片文字 |

Google Sheets 分頁名稱：精選動態標題（如 `旅遊`）

### 檔案位置

```
downloads/
├── {帳號名稱}/          ← 主頁貼文
│   ├── posts.csv
│   └── images/
│       ├── 2024-01-01_ABC123.jpg
│       └── 2024-01-02_DEF456_slide1.jpg
│
├── {short_code}/        ← 單筆貼文
│   ├── posts.csv
│   └── images/
│
└── highlights_{id}/     ← 精選動態
    └── images/
        └── {item_id}.jpg
```

## 注意事項

- **貼文分析**：僅支援公開帳號，不需登入
- **精選動態**：需要提供 Session ID；Session ID 僅用於本地請求，不會被儲存或傳送至其他地方
- Instagram 有請求頻率限制，抓取大量資料時速度較慢屬正常現象
- OCR 第一次執行時需要初始化 Apple Vision，之後會較快
