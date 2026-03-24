import os
import re
import json

import requests
import yt_dlp
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from youtube_transcript_api import YouTubeTranscriptApi


class YouTubeVideoScraper:
    def __init__(self, debug=False):
        self.debug = debug
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }

    def _get_video_id(self, url):
        """Extract video ID from YouTube URL."""
        patterns = [
            r'(?:v=|/v/|youtu\.be/|/embed/|/shorts/)([A-Za-z0-9_-]{11})',
            r'^([A-Za-z0-9_-]{11})$',
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return ""

    def _format_count(self, count):
        """Format large numbers for display."""
        if count is None:
            return "N/A"
        count = int(count)
        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.1f}B"
        elif count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M"
        elif count >= 1_000:
            return f"{count / 1_000:.1f}K"
        return str(count)

    def _format_duration(self, seconds):
        """Convert seconds to HH:MM:SS or MM:SS."""
        if not seconds:
            return "N/A"
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"

    def _to_hinglish(self, hindi_text):
        """Convert Hindi (Devanagari) text to Hinglish (Roman script)."""
        lines = []
        for line in hindi_text.split("\n"):
            converted = transliterate(line, sanscript.DEVANAGARI, sanscript.IAST)
            simple = converted
            for old, new in [
                ("ā", "aa"), ("ī", "ee"), ("ū", "oo"), ("ṛ", "ri"),
                ("ṅ", "n"), ("ñ", "n"), ("ṭ", "t"), ("ḍ", "d"),
                ("ṇ", "n"), ("ś", "sh"), ("ṣ", "sh"), ("ṃ", "n"),
                ("ḥ", "h"), ("ṁ", "n"), ("ē", "e"), ("ō", "o"),
                ("ai", "ai"), ("au", "au"),
            ]:
                simple = simple.replace(old, new)
            lines.append(simple)
        return "\n".join(lines)

    def scrape_video(self, video_url):
        """Scrape all data from a YouTube video link using yt-dlp."""
        video_url = video_url.strip()
        if not video_url.startswith("http"):
            video_url = f"https://www.youtube.com/watch?v={video_url}"

        video_id = self._get_video_id(video_url)
        result = {"url": video_url, "video_id": video_id}

        # === Step 1: Fetch video info using yt-dlp ===
        print("  [1/2] Fetching video info via yt-dlp...")
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "no_color": True,
            "extractor_args": {"youtube": {"player_client": ["mweb"]}},
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except Exception as e:
            return {"error": f"yt-dlp failed: {e}"}

        if self.debug:
            with open("debug_yt_info.json", "w", encoding="utf-8") as f:
                json.dump(ydl.sanitize_info(info), f, indent=2, ensure_ascii=False)

        # === Extract data from yt-dlp info ===
        result["title"] = info.get("title", "")
        result["channel"] = info.get("uploader", "") or info.get("channel", "")
        result["channel_id"] = info.get("channel_id", "")
        result["channel_url"] = info.get("channel_url", "") or info.get("uploader_url", "")
        result["description"] = info.get("description", "")
        result["views"] = info.get("view_count")
        result["likes"] = info.get("like_count")
        result["comment_count"] = info.get("comment_count")
        result["is_live"] = info.get("is_live", False)

        # Thumbnail
        thumbnails = info.get("thumbnails", [])
        result["thumbnail"] = thumbnails[-1]["url"] if thumbnails else ""

        # Duration
        duration_sec = info.get("duration")
        result["duration"] = duration_sec
        result["duration_formatted"] = self._format_duration(duration_sec)

        # Tags / Keywords
        result["tags"] = info.get("tags", []) or []

        # Dates
        upload_date = info.get("upload_date", "")
        if upload_date and len(upload_date) == 8:
            result["upload_date"] = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"
        else:
            result["upload_date"] = upload_date

        # Categories
        result["categories"] = info.get("categories", []) or []
        result["language"] = info.get("language", "")

        # Available subtitle languages
        subtitles_info = info.get("subtitles", {})
        auto_captions_info = info.get("automatic_captions", {})
        result["subtitle_langs"] = list(subtitles_info.keys()) if subtitles_info else []
        result["auto_caption_langs"] = list(auto_captions_info.keys()) if auto_captions_info else []

        # === Step 2: Fetch subtitles using youtube-transcript-api ===
        print("  [2/2] Fetching subtitles...")
        subtitles = {}
        try:
            ytt = YouTubeTranscriptApi()

            # List available transcripts
            transcript_list = ytt.list(video_id)
            available_langs = []
            for t in transcript_list:
                available_langs.append({"lang": t.language_code, "auto": t.is_generated})
            result["available_subtitle_langs"] = available_langs

            # Try Hindi and English first
            for lang in ["hi", "en"]:
                try:
                    transcript = ytt.fetch(video_id, languages=[lang])
                    lines = [s.text for s in transcript.snippets if s.text.strip()]
                    if lines:
                        subtitles[lang] = "\n".join(lines)
                except Exception:
                    pass

            # Fallback to first available language
            if not subtitles and available_langs:
                first_lang = available_langs[0]["lang"]
                try:
                    transcript = ytt.fetch(video_id, languages=[first_lang])
                    lines = [s.text for s in transcript.snippets if s.text.strip()]
                    if lines:
                        subtitles[first_lang] = "\n".join(lines)
                except Exception:
                    pass

            # Hinglish version from Hindi
            if "hi" in subtitles:
                subtitles["hinglish"] = self._to_hinglish(subtitles["hi"])
        except Exception:
            pass

        result["subtitles"] = subtitles

        # Extract hashtags and mentions from description
        desc = result.get("description", "")
        if desc:
            hashtags = re.findall(r'#(\w+)', desc)
            if hashtags:
                result["hashtags"] = hashtags
            mentions = re.findall(r'@([\w.]+)', desc)
            if mentions:
                result["mentions"] = mentions

        print("    OK")
        return result

    def download_thumbnail(self, result, output_dir="downloads"):
        """Download video thumbnail."""
        video_id = result.get("video_id", "video")
        save_dir = os.path.join(output_dir, video_id)
        os.makedirs(save_dir, exist_ok=True)

        thumbnail_url = result.get("thumbnail", "")
        if not thumbnail_url:
            return []

        downloaded = []
        try:
            resp = requests.get(thumbnail_url, timeout=15, headers=self.headers)
            if resp.status_code == 200:
                ext = ".jpg"
                content_type = resp.headers.get("content-type", "")
                if "webp" in content_type:
                    ext = ".webp"
                elif "png" in content_type:
                    ext = ".png"

                filepath = os.path.join(save_dir, f"thumbnail{ext}")
                with open(filepath, "wb") as f:
                    f.write(resp.content)
                downloaded.append(filepath)
        except Exception:
            pass

        return downloaded

    def extract_text_from_images(self, image_paths):
        """Extract text from downloaded images using RapidOCR."""
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            return {"error": "Install: pip install rapidocr-onnxruntime"}

        ocr = RapidOCR()
        results = {}
        for path in image_paths:
            try:
                result, _ = ocr(path)
                if result:
                    texts = [line[1] for line in result if line[1]]
                    if texts:
                        results[os.path.basename(path)] = "\n".join(texts)
            except Exception as e:
                results[os.path.basename(path)] = f"[Error: {str(e)}]"

        return results
