from fastapi import FastAPI
from .routes import router

app = FastAPI(
    title="Social Media Scraper API",
    description="Scrape Instagram posts and YouTube videos by URL",
    version="1.0.0",
)

app.include_router(router)
