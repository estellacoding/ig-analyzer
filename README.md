# Instagram Analyzer

抓取公開 IG 帳號貼文資料、圖片文字辨識，自動同步至 Google Sheets。

## 功能

- 抓取公開 Instagram 帳號的所有貼文資料（不需登入）
- 支援篩選日期範圍，只抓取指定期間的貼文
- 支援單筆貼文抓取
- 自動下載貼文圖片與影片
- 使用 Apple Vision OCR 辨識圖片中的文字（支援繁體中文）
- 將結果匯出為 CSV（Excel/Google Sheets 相容）
- 自動同步至 Google Sheets，具備增量更新機制（只新增未存在的貼文）

## 環境需求

- macOS（OCR 使用 Apple Vision，僅支援 macOS）
- Python 3.12+

## 安裝

```bash
git clone https://github.com/estellacoding/ig-analyzer.git
cd ig-analyzer

python -m venv venv
source venv/bin/activate
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
source venv/bin/activate
python app.py
```

開啟瀏覽器至 `http://localhost:8080`

### 抓取主頁所有貼文

1. 貼上 Instagram 主頁 URL，例如 `https://www.instagram.com/yourusername`
2. 選填日期範圍（不填則抓全部）
3. 點擊「下載貼文」

### 抓取單筆貼文

1. 貼上單篇貼文 URL，例如 `https://www.instagram.com/p/ABC123/`
2. 點擊「下載單筆貼文資料」

## 輸出格式

### CSV 欄位

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

### 檔案位置

抓取主頁所有貼文：

```
downloads/
└── {帳號名稱}/
    ├── posts.csv
    └── images/
        ├── 2024-01-01_ABC123.jpg
        └── 2024-01-02_DEF456_slide1.jpg
```

抓取單筆貼文：

```
downloads/
└── {short_code}/
    ├── posts.csv
    └── images/
        └── 2024-01-01_{short_code}.jpg
```

## 注意事項

- 僅支援**公開帳號**（不需登入，帳號安全無虞）
- Instagram 有請求頻率限制，抓取大量貼文時速度較慢屬正常現象
- OCR 第一次執行時需要初始化 Apple Vision，之後會較快
