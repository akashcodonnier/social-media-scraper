import os
import re
import json

import requests
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
from youtube_transcript_api import YouTubeTranscriptApi


class YouTubeVideoScraper:
    def __init__(self, debug=False):
        self.debug = debug
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _clean_url(self, url):
        """Clean YouTube URL."""
        url = url.strip()
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"
        return url

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

    def _parse_count_text(self, text):
        """Parse count from text like '7,511,234 views' or '193K likes'."""
        if not text:
            return None
        text = text.strip().replace(",", "")
        match = re.search(r'([\d.]+)\s*([KMB]?)', text, re.IGNORECASE)
        if match:
            num = float(match.group(1))
            suffix = match.group(2).upper()
            mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
            return int(num * mult)
        return None

    def _parse_iso_duration(self, duration_str):
        """Parse ISO 8601 duration like PT30M13S to seconds."""
        if not duration_str:
            return None
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
        if match:
            h = int(match.group(1) or 0)
            m = int(match.group(2) or 0)
            s = int(match.group(3) or 0)
            return h * 3600 + m * 60 + s
        return None

    def _extract_json_from_html(self, html, var_name):
        """Extract JSON object assigned to a JS variable in HTML."""
        pattern = rf'var\s+{var_name}\s*=\s*(\{{.*?\}});'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try alternative pattern (without var)
        pattern = rf'{var_name}\s*=\s*(\{{.*?\}});'
        match = re.search(pattern, html, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        return None

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
        """Scrape all data from a YouTube video link."""
        url = self._clean_url(video_url)
        video_id = self._get_video_id(url)
        watch_url = f"https://www.youtube.com/watch?v={video_id}"
        result = {"url": url, "video_id": video_id}

        # === Step 1: Fetch page HTML ===
        print("  [1/2] Fetching YouTube page...")
        try:
            resp = requests.get(watch_url, headers=self.headers, timeout=15)
            html = resp.text
        except Exception as e:
            return {"error": f"Failed to fetch page: {e}"}

        if self.debug:
            with open("debug_yt_page.html", "w", encoding="utf-8") as f:
                f.write(html)
            print("    (saved debug_yt_page.html)")

        # === Step 2: Extract JSON data from page ===
        print("  [2/2] Parsing video data...")

        initial_data = self._extract_json_from_html(html, "ytInitialData")
        player_response = self._extract_json_from_html(html, "ytInitialPlayerResponse")

        if self.debug:
            if initial_data:
                with open("debug_yt_initial_data.json", "w", encoding="utf-8") as f:
                    json.dump(initial_data, f, indent=2, ensure_ascii=False)
            if player_response:
                with open("debug_yt_player_response.json", "w", encoding="utf-8") as f:
                    json.dump(player_response, f, indent=2, ensure_ascii=False)
            print("    (saved debug JSON files)")

        # --- From playerResponse ---
        if player_response:
            video_details = player_response.get("videoDetails", {})
            microformat = player_response.get("microformat", {}).get(
                "playerMicroformatRenderer", {}
            )

            result["title"] = video_details.get("title", "")
            result["channel"] = video_details.get("author", "")
            result["channel_id"] = video_details.get("channelId", "")
            result["description"] = video_details.get("shortDescription", "")
            result["views"] = int(video_details.get("viewCount", 0)) or None
            result["is_live"] = video_details.get("isLiveContent", False)
            result["thumbnail"] = video_details.get("thumbnail", {}).get(
                "thumbnails", [{}]
            )[-1].get("url", "")

            # Duration
            duration_sec = int(video_details.get("lengthSeconds", 0)) or None
            result["duration"] = duration_sec
            result["duration_formatted"] = self._format_duration(duration_sec)

            # Tags / Keywords
            result["tags"] = video_details.get("keywords", [])

            # From microformat
            result["channel_url"] = microformat.get("ownerProfileUrl", "")
            result["upload_date"] = microformat.get("publishDate", "")
            result["categories"] = [microformat.get("category", "")] if microformat.get("category") else []
            result["language"] = microformat.get("defaultAudioLanguage", "")

            # Subtitles / Captions (from page data for language list)
            captions_data = player_response.get("captions", {}).get(
                "playerCaptionsTracklistRenderer", {}
            )
            caption_tracks = captions_data.get("captionTracks", [])

            result["subtitle_langs"] = []
            result["auto_caption_langs"] = []

            for track in caption_tracks:
                lang_code = track.get("languageCode", "")
                is_auto = track.get("kind") == "asr"
                if is_auto:
                    result["auto_caption_langs"].append(lang_code)
                else:
                    result["subtitle_langs"].append(lang_code)

        # Fetch actual subtitle text using youtube-transcript-api
        subtitles = {}
        try:
            ytt = YouTubeTranscriptApi()
            for lang in ["hi", "en"]:
                try:
                    transcript = ytt.fetch(video_id, languages=[lang])
                    lines = [s.text for s in transcript.snippets if s.text.strip()]
                    if lines:
                        subtitles[f"{lang} (auto)"] = "\n".join(lines)
                except Exception:
                    pass

            # Add Hinglish version
            for key, text in list(subtitles.items()):
                if key.startswith("hi"):
                    subtitles["hinglish"] = self._to_hinglish(text)
                    break
        except Exception:
            pass

        result["subtitles"] = subtitles

        # --- From initialData (likes, comment count) ---
        if initial_data:
            try:
                # Navigate to primary results
                contents = (
                    initial_data.get("contents", {})
                    .get("twoColumnWatchNextResults", {})
                    .get("results", {})
                    .get("results", {})
                    .get("contents", [])
                )

                for item in contents:
                    # Video primary info
                    primary = item.get("videoPrimaryInfoRenderer", {})
                    if primary:
                        # Likes
                        menu_items = (
                            primary.get("videoActions", {})
                            .get("menuRenderer", {})
                            .get("topLevelButtons", [])
                        )
                        for btn in menu_items:
                            toggle = btn.get("segmentedLikeDislikeButtonViewModel", {})
                            like_btn = toggle.get("likeButtonViewModel", {}).get(
                                "likeButtonViewModel", {}
                            )
                            like_count_str = like_btn.get("toggleButtonViewModel", {}).get(
                                "toggleButtonViewModel", {}
                            ).get("defaultButtonViewModel", {}).get(
                                "buttonViewModel", {}
                            ).get("title", "")
                            if like_count_str:
                                result["likes"] = self._parse_count_text(like_count_str)

                        # Date
                        date_text = primary.get("dateText", {}).get("simpleText", "")
                        if date_text:
                            result["date_text"] = date_text

                    # Video secondary info - comment count
                    section = item.get("itemSectionRenderer", {})
                    section_contents = section.get("contents", [])
                    for sc in section_contents:
                        comment_header = sc.get("commentsEntryPointHeaderRenderer", {})
                        if comment_header:
                            count_text = comment_header.get("commentCount", {}).get("simpleText", "")
                            if count_text:
                                result["comment_count"] = self._parse_count_text(count_text)

            except Exception:
                pass

        # --- Fallback: meta tags from HTML ---
        if not result.get("title"):
            match = re.search(r'<meta\s+name="title"\s+content="([^"]*)"', html)
            if match:
                result["title"] = match.group(1)

        if not result.get("description"):
            match = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', html)
            if match:
                result["description"] = match.group(1)

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
