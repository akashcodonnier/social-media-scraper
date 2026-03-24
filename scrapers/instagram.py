import os
import re
import time
import html as html_lib

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager


class InstagramPostScraper:
    def __init__(self, debug=False):
        self.driver = None
        self.debug = debug

    def _start_browser(self):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--single-process")
        options.add_argument("--disable-setuid-sandbox")
        options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Use system Chrome in Docker, else auto-detect with webdriver-manager
        chrome_bin = os.environ.get("CHROME_BIN")
        if chrome_bin:
            options.binary_location = chrome_bin

        try:
            # Try direct Chrome (works in Docker with system-installed Chrome)
            self.driver = webdriver.Chrome(options=options)
        except Exception:
            # Fallback to webdriver-manager (local development)
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)

        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
        )

    def _close_browser(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def _clean_url(self, url):
        """Clean Instagram post URL - remove query params."""
        url = url.strip().rstrip("/")
        if not url.startswith("http"):
            url = f"https://www.instagram.com/p/{url}"
        if "?" in url:
            url = url.split("?")[0]
        return url.rstrip("/") + "/"

    def _get_shortcode(self, url):
        """Extract shortcode from Instagram URL."""
        match = re.search(r"/(?:p|reel|tv)/([A-Za-z0-9_-]+)", url)
        return match.group(1) if match else ""

    def _parse_count(self, text):
        """Parse count strings like '1.2M', '500K', '1,234'."""
        if not text:
            return text
        text = str(text).strip().replace(",", "")
        for suffix, mult in {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.items():
            if text.upper().endswith(suffix):
                try:
                    return str(int(float(text[:-1]) * mult))
                except ValueError:
                    pass
        return text

    def _extract_meta_from_html(self, page_source):
        """Parse meta tags directly from HTML source (more reliable than Selenium DOM)."""
        metas = {}
        # Match both orders: property then content, and content then property
        for match in re.finditer(
            r'<meta\s+[^>]*(?:property|name)=["\']([^"\']+)["\'][^>]*content=["\']([^"\']*)["\']',
            page_source,
        ):
            metas[match.group(1)] = html_lib.unescape(match.group(2))

        for match in re.finditer(
            r'<meta\s+[^>]*content=["\']([^"\']*)["\'][^>]*(?:property|name)=["\']([^"\']+)["\']',
            page_source,
        ):
            metas[match.group(2)] = html_lib.unescape(match.group(1))

        return metas

    def _fetch_oembed(self, url):
        """Use Instagram's public oEmbed API."""
        try:
            oembed_url = f"https://www.instagram.com/api/v1/oembed/?url={url}"
            resp = requests.get(oembed_url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
            })
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def scrape_post(self, post_url):
        """Scrape all data from an Instagram post link."""
        url = self._clean_url(post_url)
        shortcode = self._get_shortcode(url)
        result = {"url": url, "shortcode": shortcode}

        # === Method 1: oEmbed API ===
        print("  [1/2] Trying oEmbed API...")
        oembed = self._fetch_oembed(url)
        if oembed:
            result["author"] = oembed.get("author_name", "")
            result["author_url"] = oembed.get("author_url", "")
            result["caption"] = oembed.get("title", "")
            result["media_url"] = oembed.get("thumbnail_url", "")
            result["thumbnail_width"] = oembed.get("thumbnail_width", "")
            result["thumbnail_height"] = oembed.get("thumbnail_height", "")

            # Extract full caption from embed HTML
            embed_html = oembed.get("html", "")
            if embed_html:
                # The embed HTML sometimes has more caption text
                caption_match = re.search(
                    r'data-instgrm-captioned', embed_html
                )
                if caption_match:
                    result["has_caption"] = True

            print("    OK")
        else:
            print("    Failed")

        # === Method 2: Fetch HTML with requests (lightweight, no Chrome needed) ===
        print("  [2/3] Fetching page HTML...")
        try:
            resp = requests.get(url, timeout=15, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            })
            page_source = resp.text

            if self.debug:
                with open("debug_page.html", "w", encoding="utf-8") as f:
                    f.write(page_source)

            # --- Parse meta tags from raw HTML ---
            metas = self._extract_meta_from_html(page_source)

            og_title = metas.get("og:title", "")
            og_desc = metas.get("og:description", metas.get("description", ""))
            og_image = metas.get("og:image", "")
            og_video = metas.get("og:video", "")

            # Image
            if og_image and not result.get("media_url"):
                result["media_url"] = og_image

            # Video
            if og_video:
                result["video_url"] = og_video
                result["media_type"] = "Video"
            elif not result.get("media_type"):
                result["media_type"] = "Image"

            # Author & Caption from title
            if og_title:
                match = re.match(
                    r'^(.*?)\s+on Instagram:\s*["\u201c](.*?)["\u201d]\s*$',
                    og_title, re.DOTALL
                )
                if match:
                    if not result.get("author"):
                        result["author"] = match.group(1).strip()
                    caption_from_title = match.group(2).strip()
                    if not result.get("caption") or len(caption_from_title) > len(result.get("caption", "")):
                        result["caption"] = caption_from_title

            # Likes, Comments, Date from description
            if og_desc:
                likes_m = re.search(r'([\d,.]+[KMB]?)\s*likes?', og_desc, re.IGNORECASE)
                comments_m = re.search(r'([\d,.]+[KMB]?)\s*comments?', og_desc, re.IGNORECASE)
                if likes_m:
                    result["likes"] = self._parse_count(likes_m.group(1))
                if comments_m:
                    result["comments"] = self._parse_count(comments_m.group(1))

                date_m = re.search(
                    r'on\s+((?:January|February|March|April|May|June|July|August|'
                    r'September|October|November|December)\s+\d{1,2},\s+\d{4})',
                    og_desc
                )
                if date_m:
                    result["post_date"] = date_m.group(1)

            print("    OK")
        except Exception as e:
            print(f"    HTML fetch failed: {e}")

        # === Method 3: Selenium (only if CHROME_BIN not set = local dev) ===
        use_selenium = not os.environ.get("SKIP_SELENIUM")
        if use_selenium:
            print("  [3/3] Loading page with Selenium...")
            try:
                self._start_browser()
                self.driver.set_page_load_timeout(30)
                self.driver.get(url)
                time.sleep(3)

                page_source = self.driver.page_source

                # --- Try to get date from DOM ---
                if "post_date" not in result:
                    try:
                        time_el = self.driver.find_element(By.CSS_SELECTOR, "time[datetime]")
                        result["post_date"] = time_el.get_attribute("datetime")
                    except Exception:
                        pass

                # --- Try to get images from DOM ---
                try:
                    img_els = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        'img[src*="cdninstagram"], img[src*="instagram"]'
                    )
                    dom_images = []
                    seen = set()
                    for img in img_els:
                        src = img.get_attribute("src") or ""
                        alt = img.get_attribute("alt") or ""
                        if (src and src not in seen
                                and "s150x150" not in src
                                and "44x44" not in src
                                and "/rsrc.php" not in src):
                            seen.add(src)
                            dom_images.append({
                                "media_url": src,
                                "alt_text": alt,
                                "is_video": False,
                            })
                    if dom_images:
                        result["all_images"] = dom_images
                        for img_data in dom_images:
                            alt = img_data.get("alt_text", "")
                            if alt and len(alt) > 30:
                                result["image_alt"] = alt
                                mentions = re.findall(r'@([\w.]+)', alt)
                                if mentions:
                                    result["mentions_from_alt"] = mentions
                                break
                except Exception:
                    pass

                print("    OK")
            except Exception as e:
                print(f"    Selenium failed: {e}")
            finally:
                self._close_browser()
        else:
            print("  [3/3] Selenium skipped (server mode)")

        # --- Extract hashtags and mentions from caption ---
        caption = result.get("caption", "")
        if caption:
            hashtags = re.findall(r'#(\w+)', caption)
            if hashtags:
                result["hashtags"] = hashtags

            mentions = re.findall(r'@([\w.]+)', caption)
            if mentions:
                result["mentions"] = mentions

        return result

    def download_images(self, result, output_dir="downloads"):
        """Download all images from scraped post data."""
        shortcode = result.get("shortcode", "post")
        save_dir = os.path.join(output_dir, shortcode)
        os.makedirs(save_dir, exist_ok=True)

        # Collect image URLs (prefer DOM images, fallback to thumbnail)
        image_urls = []
        all_images = result.get("all_images", [])
        if all_images:
            # Only take first 2 images (actual post images, not suggested posts)
            # We filter by checking if they're from the same post
            for img in all_images:
                image_urls.append(img.get("media_url", ""))
        elif result.get("media_url"):
            image_urls.append(result["media_url"])

        downloaded = []
        for i, url in enumerate(image_urls):
            if not url:
                continue
            try:
                resp = requests.get(url, timeout=15, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                  "AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36"
                })
                if resp.status_code == 200:
                    # Determine extension
                    ext = ".jpg"
                    content_type = resp.headers.get("content-type", "")
                    if "webp" in content_type or url.endswith(".webp"):
                        ext = ".webp"
                    elif "png" in content_type:
                        ext = ".png"

                    filepath = os.path.join(save_dir, f"image_{i+1}{ext}")
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
