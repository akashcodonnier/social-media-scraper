from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool

from .models import ScrapeRequest, ScrapeResponse
from .url_detector import detect_platform
from scrapers import InstagramPostScraper, YouTubeVideoScraper

router = APIRouter()


def _scrape_instagram(request: ScrapeRequest) -> ScrapeResponse:
    """Run Instagram scraping (blocking, runs in threadpool)."""
    scraper = InstagramPostScraper(debug=request.debug)
    data = scraper.scrape_post(request.url)

    if "error" in data:
        return ScrapeResponse(
            success=False, platform="instagram", url=request.url,
            data={}, error=data["error"],
        )

    downloaded = []
    ocr_results = {}

    if request.download_images:
        downloaded = scraper.download_images(data)

    if request.run_ocr and downloaded:
        ocr_results = scraper.extract_text_from_images(downloaded)

    return ScrapeResponse(
        success=True, platform="instagram", url=request.url,
        data=data, downloaded_images=downloaded, ocr_results=ocr_results,
    )


def _scrape_youtube(request: ScrapeRequest) -> ScrapeResponse:
    """Run YouTube scraping."""
    scraper = YouTubeVideoScraper(debug=request.debug)
    data = scraper.scrape_video(request.url)

    if "error" in data:
        return ScrapeResponse(
            success=False, platform="youtube", url=request.url,
            data={}, error=data["error"],
        )

    downloaded = []
    ocr_results = {}

    if request.download_images:
        downloaded = scraper.download_thumbnail(data)

    if request.run_ocr and downloaded:
        ocr_results = scraper.extract_text_from_images(downloaded)

    return ScrapeResponse(
        success=True, platform="youtube", url=request.url,
        data=data, downloaded_images=downloaded, ocr_results=ocr_results,
    )


@router.post("/scrape", response_model=ScrapeResponse)
async def scrape_url(request: ScrapeRequest):
    """Auto-detect platform and scrape data from URL."""
    if request.run_ocr:
        request.download_images = True
    platform = detect_platform(request.url)

    if platform is None:
        raise HTTPException(
            status_code=400,
            detail="Unsupported URL. Provide an Instagram post or YouTube video URL.",
        )

    if platform == "instagram":
        return await run_in_threadpool(_scrape_instagram, request)
    else:
        return await run_in_threadpool(_scrape_youtube, request)


@router.post("/scrape/instagram", response_model=ScrapeResponse)
async def scrape_instagram(request: ScrapeRequest):
    """Force Instagram scraping."""
    return await run_in_threadpool(_scrape_instagram, request)


@router.post("/scrape/youtube", response_model=ScrapeResponse)
async def scrape_youtube(request: ScrapeRequest):
    """Force YouTube scraping."""
    return await run_in_threadpool(_scrape_youtube, request)


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "platforms": ["instagram", "youtube"]}
