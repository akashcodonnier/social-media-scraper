import re


def detect_platform(url: str) -> str | None:
    """Detect whether a URL is Instagram or YouTube."""
    url = url.strip().lower()

    # Instagram patterns
    if re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[A-Za-z0-9_-]+', url, re.IGNORECASE):
        return "instagram"

    # YouTube patterns
    if re.search(
        r'(youtube\.com/watch\?|youtube\.com/shorts/|youtu\.be/|youtube\.com/embed/|youtube\.com/v/)',
        url, re.IGNORECASE,
    ):
        return "youtube"

    return None
