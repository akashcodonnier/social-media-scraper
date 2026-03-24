# Social Media Scraper API

FastAPI-based REST API that scrapes public Instagram posts and YouTube videos. Auto-detects the platform from the URL.

## Features

### Instagram
- Post metadata — author, caption, likes, comments, date, media type
- Hashtags & mentions from caption
- Image download + OCR (RapidOCR)

### YouTube
- Video metadata — title, channel, views, likes, duration, tags, category
- Full subtitles (Hindi, English, Hinglish transliteration)
- Thumbnail download + OCR

## Setup

```bash
pip install -r requirements.txt
```

### Requirements
- Python 3.10+
- Google Chrome (for Instagram scraping)

## Usage

Start the API server:

```bash
python main.py
```

Server runs at `http://localhost:8000`

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/scrape` | Auto-detect platform, scrape URL |
| POST | `/scrape/instagram` | Force Instagram scraping |
| POST | `/scrape/youtube` | Force YouTube scraping |
| GET | `/health` | Health check |

### Request Body

```json
{
    "url": "https://www.instagram.com/p/ABC123/",
    "download_images": true,
    "run_ocr": true,
    "debug": false
}
```

### Example

```bash
# Instagram
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.instagram.com/p/ABC123/"}'

# YouTube
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtu.be/FwQsEMmDq1Y"}'

# YouTube Shorts
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/shorts/7fLqPBK_Z9o"}'
```

### Response

```json
{
    "success": true,
    "platform": "instagram",
    "url": "https://www.instagram.com/p/ABC123/",
    "data": { "...scraped data..." },
    "downloaded_images": ["downloads/ABC123/image_1.jpg"],
    "ocr_results": {"image_1.jpg": "text from image"},
    "error": null
}
```

### Docs

FastAPI auto-generates API docs at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Project Structure

```
├── scrapers/
│   ├── instagram.py    # Instagram scraper (oEmbed + Selenium)
│   └── youtube.py      # YouTube scraper (HTML parsing + transcript API)
├── api/
│   ├── app.py          # FastAPI app
│   ├── routes.py       # API endpoints
│   ├── models.py       # Request/Response models
│   └── url_detector.py # URL platform detection
├── main.py             # Server entrypoint
└── requirements.txt
```

## How It Works

**Instagram:** `oEmbed API → Selenium (HTML meta tags + DOM) → Image download → OCR`

**YouTube:** `requests (HTML fetch) → JSON parse (ytInitialPlayerResponse) → Transcript API → Thumbnail download → OCR`

Both use web scraping (HTML parsing) — no login or API key required.
