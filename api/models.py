from pydantic import BaseModel
from typing import Optional


class ScrapeRequest(BaseModel):
    url: str
    download_images: bool = True
    run_ocr: bool = True
    debug: bool = False


class ScrapeResponse(BaseModel):
    success: bool
    platform: str
    url: str
    data: dict
    downloaded_images: list[str] = []
    ocr_results: dict[str, str] = {}
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    platform: Optional[str] = None
