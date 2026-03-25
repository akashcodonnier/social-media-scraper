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

    def _fetch_innertube_player(self, video_id):
        """Fetch video info via YouTube Innertube Player API (Android client)."""
        api_key = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
        url = f"https://www.youtube.com/youtubei/v1/player?key={api_key}"
        payload = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "ANDROID",
                    "clientVersion": "20.10.38",
                    "androidSdkVersion": 30,
                    "hl": "en",
                    "gl": "US",
                }
            },
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "com.google.android.youtube/20.10.38 (Linux; U; Android 11) gzip",
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return resp.json()

    def _fetch_innertube_web(self, video_id):
        """Fetch caption data via Innertube WEB client (returns subtitle tracks)."""
        url = "https://www.youtube.com/youtubei/v1/player"
        payload = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "WEB_EMBEDDED_PLAYER",
                    "clientVersion": "1.20231219.01.00",
                    "hl": "en",
                    "gl": "US",
                }
            },
            "thirdParty": {
                "embedUrl": "https://www.google.com"
            },
        }
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.headers["User-Agent"],
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        return resp.json()

    def _fetch_caption_tracks_from_page(self, video_id):
        """Fetch caption tracks from YouTube watch page (works for Shorts too)."""
        try:
            url = f"https://www.youtube.com/watch?v={video_id}"
            resp = requests.get(url, timeout=15, headers={
                **self.headers,
                "Cookie": "CONSENT=YES+1",
            })
            match = re.search(
                r'"captions":\s*(\{.*?"playerCaptionsTracklistRenderer".*?\})\s*,\s*"videoDetails"',
                resp.text, re.DOTALL
            )
            if match:
                captions = json.loads(match.group(1))
                return captions.get("playerCaptionsTracklistRenderer", {}).get("captionTracks", [])
        except Exception:
            pass
        return []

    def _fetch_subtitles_from_url(self, base_url):
        """Fetch subtitle text from YouTube caption URL."""
        try:
            # Add fmt=json3 for JSON format
            sep = "&" if "?" in base_url else "?"
            url = f"{base_url}{sep}fmt=json3"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                events = data.get("events", [])
                lines = []
                for event in events:
                    segs = event.get("segs", [])
                    text = "".join(s.get("utf8", "") for s in segs).strip()
                    if text and text != "\n":
                        lines.append(text)
                return "\n".join(lines)
        except Exception:
            pass
        return ""

    def _fetch_oembed(self, video_id):
        """Fetch basic info via YouTube oEmbed API (always works)."""
        url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
        try:
            resp = requests.get(url, timeout=10, headers=self.headers)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def scrape_video(self, video_url):
        """Scrape all data from a YouTube video link."""
        video_url = video_url.strip()
        if not video_url.startswith("http"):
            video_url = f"https://www.youtube.com/watch?v={video_url}"

        video_id = self._get_video_id(video_url)
        result = {"url": video_url, "video_id": video_id}

        # === Step 1: Innertube Player API ===
        print("  [1/3] Fetching video info via Innertube API...")
        try:
            player = self._fetch_innertube_player(video_id)

            if self.debug:
                with open("debug_yt_innertube.json", "w", encoding="utf-8") as f:
                    json.dump(player, f, indent=2, ensure_ascii=False)

            video_details = player.get("videoDetails", {})
            microformat = player.get("microformat", {}).get("playerMicroformatRenderer", {})

            if video_details:
                result["title"] = video_details.get("title", "")
                result["channel"] = video_details.get("author", "")
                result["channel_id"] = video_details.get("channelId", "")
                result["description"] = video_details.get("shortDescription", "")
                result["views"] = int(video_details.get("viewCount", 0)) or None
                result["is_live"] = video_details.get("isLiveContent", False)
                result["tags"] = video_details.get("keywords", [])

                # Thumbnail
                thumbnails = video_details.get("thumbnail", {}).get("thumbnails", [])
                result["thumbnail"] = thumbnails[-1]["url"] if thumbnails else ""

                # Duration
                duration_sec = int(video_details.get("lengthSeconds", 0)) or None
                result["duration"] = duration_sec
                result["duration_formatted"] = self._format_duration(duration_sec)

            if microformat:
                result["channel_url"] = microformat.get("ownerProfileUrl", "")
                result["upload_date"] = microformat.get("publishDate", "")
                result["categories"] = [microformat.get("category", "")] if microformat.get("category") else []
                result["language"] = microformat.get("defaultAudioLanguage", "")

            # Caption tracks info
            captions_data = player.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
            caption_tracks = captions_data.get("captionTracks", [])
            result["subtitle_langs"] = []
            result["auto_caption_langs"] = []
            for track in caption_tracks:
                lang_code = track.get("languageCode", "")
                if track.get("kind") == "asr":
                    result["auto_caption_langs"].append(lang_code)
                else:
                    result["subtitle_langs"].append(lang_code)

            print("    OK")
        except Exception as e:
            print(f"    Innertube failed: {e}")

        # === Step 2: oEmbed fallback for basic info ===
        if not result.get("title"):
            print("  [2/3] Trying oEmbed API fallback...")
            oembed = self._fetch_oembed(video_id)
            if oembed:
                result["title"] = oembed.get("title", "")
                result["channel"] = oembed.get("author_name", "")
                result["channel_url"] = oembed.get("author_url", "")
                result["thumbnail"] = oembed.get("thumbnail_url", "")
                print("    OK")
            else:
                print("    Failed")
        else:
            print("  [2/3] oEmbed skipped (Innertube data available)")

        # === Step 3: Fetch subtitles ===
        print("  [3/3] Fetching subtitles...")
        subtitles = {}
        caption_tracks = []

        # Method A: Get caption tracks from Innertube WEB_EMBEDDED client
        try:
            web_player = self._fetch_innertube_web(video_id)
            web_captions = web_player.get("captions", {}).get("playerCaptionsTracklistRenderer", {})
            caption_tracks = web_captions.get("captionTracks", [])

            if self.debug:
                with open("debug_yt_web_captions.json", "w", encoding="utf-8") as f:
                    json.dump(web_captions, f, indent=2, ensure_ascii=False)

            # Update caption lang info
            if caption_tracks:
                result["subtitle_langs"] = []
                result["auto_caption_langs"] = []
                for track in caption_tracks:
                    lang_code = track.get("languageCode", "")
                    if track.get("kind") == "asr":
                        result["auto_caption_langs"].append(lang_code)
                    else:
                        result["subtitle_langs"].append(lang_code)
        except Exception:
            pass

        # Method A2: Get caption tracks from YouTube watch page (works for Shorts)
        if not caption_tracks:
            try:
                page_tracks = self._fetch_caption_tracks_from_page(video_id)
                if page_tracks:
                    caption_tracks = page_tracks
                    result["subtitle_langs"] = []
                    result["auto_caption_langs"] = []
                    for track in caption_tracks:
                        lang_code = track.get("languageCode", "")
                        if track.get("kind") == "asr":
                            result["auto_caption_langs"].append(lang_code)
                        else:
                            result["subtitle_langs"].append(lang_code)
            except Exception:
                pass

        # Method B: Fetch subtitle text directly from caption URLs
        if caption_tracks:
            # Prioritize: hi, en, then any available
            priority_langs = ["hi", "en"]
            track_map = {t.get("languageCode", ""): t for t in caption_tracks}

            for lang in priority_langs:
                if lang in track_map:
                    base_url = track_map[lang].get("baseUrl", "")
                    if base_url:
                        text = self._fetch_subtitles_from_url(base_url)
                        if text:
                            subtitles[lang] = text

            # If no hi/en, fetch first available
            if not subtitles and caption_tracks:
                first_track = caption_tracks[0]
                lang = first_track.get("languageCode", "unknown")
                base_url = first_track.get("baseUrl", "")
                if base_url:
                    text = self._fetch_subtitles_from_url(base_url)
                    if text:
                        subtitles[lang] = text

        # Method C: Fallback to youtube-transcript-api
        if not subtitles:
            try:
                ytt = YouTubeTranscriptApi()
                transcript_list = ytt.list(video_id)
                available_langs = []
                for t in transcript_list:
                    available_langs.append({"lang": t.language_code, "auto": t.is_generated})

                for lang in ["hi", "en"]:
                    try:
                        transcript = ytt.fetch(video_id, languages=[lang])
                        lines = [s.text for s in transcript.snippets if s.text.strip()]
                        if lines:
                            subtitles[lang] = "\n".join(lines)
                    except Exception:
                        pass

                if not subtitles and available_langs:
                    first_lang = available_langs[0]["lang"]
                    try:
                        transcript = ytt.fetch(video_id, languages=[first_lang])
                        lines = [s.text for s in transcript.snippets if s.text.strip()]
                        if lines:
                            subtitles[first_lang] = "\n".join(lines)
                    except Exception:
                        pass
            except Exception:
                pass

        # Add Hinglish version from Hindi
        if "hi" in subtitles:
            subtitles["hinglish"] = self._to_hinglish(subtitles["hi"])

        if subtitles:
            print("    OK")
        else:
            print("    No subtitles found")

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
