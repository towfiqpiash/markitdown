import time
import re
import bs4
from typing import Any, BinaryIO, Dict, List, Union
from urllib.parse import parse_qs, urlparse, unquote

from .._base_converter import DocumentConverter, DocumentConverterResult
from .._stream_info import StreamInfo

# Optional YouTube transcription support
try:
    # Suppress some warnings on library import
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        # Patch submitted upstream to fix the SyntaxWarning
        from youtube_transcript_api import YouTubeTranscriptApi

    IS_YOUTUBE_TRANSCRIPT_CAPABLE = True
except ModuleNotFoundError:
    IS_YOUTUBE_TRANSCRIPT_CAPABLE = False


ACCEPTED_MIME_TYPE_PREFIXES = [
    "text/html",
    "application/xhtml",
]

ACCEPTED_FILE_EXTENSIONS = [
    ".html",
    ".htm",
]


class YouTubeConverter(DocumentConverter):
    """Handle YouTube specially, focusing on the video title, description, and transcript."""

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,  # Options to pass to the converter
    ) -> bool:
        """
        Make sure we're dealing with HTML content *from* YouTube.
        """
        url = stream_info.url or ""
        mimetype = (stream_info.mimetype or "").lower()
        extension = (stream_info.extension or "").lower()

        url = unquote(url)
        url = url.replace(r"\?", "?").replace(r"\=", "=")

        netloc = urlparse(url).netloc
        if not (netloc.endswith("youtube.com") or netloc.endswith("youtu.be")):
            return False

        if self._extract_video_id(url) is not None:
            return True

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True

        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True

        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,  # Options to pass to the converter
    ) -> DocumentConverterResult:
        import json
        import urllib.request

        url = stream_info.url or ""
        video_id = self._extract_video_id(url)

        # 1. Fetch official YouTube oEmbed metadata for title, channel, and thumbnail
        oembed_data: Dict[str, Any] = {}
        if video_id:
            try:
                oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json"
                req = urllib.request.Request(
                    oembed_url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    oembed_data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"Error fetching YouTube oEmbed metadata: {e}")

        # 2. Parse HTML stream for meta tags if available
        metadata: Dict[str, str] = {}
        try:
            encoding = "utf-8" if stream_info.charset is None else stream_info.charset
            soup = bs4.BeautifulSoup(file_stream, "html.parser", from_encoding=encoding)

            if soup.title and soup.title.string:
                metadata["title"] = soup.title.string

            for meta in soup(["meta"]):
                if not isinstance(meta, bs4.Tag):
                    continue

                for a in meta.attrs:
                    if a in ["itemprop", "property", "name"]:
                        key = str(meta.get(a, ""))
                        content = str(meta.get("content", ""))
                        if key and content:
                            metadata[key] = content
                        break

            # Capture default audio language
            for script in soup(["script"]):
                if not isinstance(script, bs4.Tag) or not script.string:
                    continue
                match = re.search(
                    r'"defaultAudioLanguage"\s*:\s*"([A-Za-z-]+)"', script.string
                )
                if match:
                    metadata["defaultAudioLanguage"] = match.group(1)
                    break
        except Exception as e:
            print(f"Error extracting metadata from HTML stream: {e}")

        # Determine video title
        title = oembed_data.get("title")
        if not title or str(title).strip().lower() in ["- youtube", "youtube"]:
            title = self._get(metadata, ["title", "og:title", "name"])
        if not title or str(title).strip().lower() in ["- youtube", "youtube"]:
            title = f"YouTube Video ({video_id})" if video_id else "YouTube Video"

        # Prepare Markdown Content
        webpage_text = f"# {title}\n\n"

        author_name = oembed_data.get("author_name") or metadata.get("author") or metadata.get("og:site_name")
        author_url = oembed_data.get("author_url")
        if author_name:
            if author_url:
                webpage_text += f"**Channel:** [{author_name}]({author_url})\n\n"
            else:
                webpage_text += f"**Channel:** {author_name}\n\n"

        thumb_url = oembed_data.get("thumbnail_url") or metadata.get("og:image")
        if thumb_url:
            webpage_text += f"![Thumbnail]({thumb_url})\n\n"

        if url:
            webpage_text += f"[Watch on YouTube]({url})\n\n"

        # Fetch full video description & chapters via Innertube API if missing
        description = metadata.get("description") or metadata.get("og:description")
        if (not description or not description.strip()) and video_id:
            innertube_info = self._fetch_innertube_details(video_id)
            description = innertube_info.get("description")

        if description and description.strip():
            webpage_text += f"### Video Overview & Description\n{description.strip()}\n\n"

        # 3. Attempt Transcript Fetching
        transcript_text = ""
        if IS_YOUTUBE_TRANSCRIPT_CAPABLE and video_id:
            try:
                import requests
                sess = requests.Session()
                sess.headers.update({
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                })
                ytt_api = YouTubeTranscriptApi(http_client=sess)
                transcript_list = ytt_api.list(video_id)

                languages = kwargs.get("youtube_transcript_languages")
                if not languages:
                    default_lang = self._get(metadata, ["defaultAudioLanguage"])
                    default_variants = [default_lang, default_lang.split("-")[0]] if default_lang else []
                    manual = [
                        t.language_code
                        for t in transcript_list
                        if not t.is_generated
                    ]
                    generated = [
                        t.language_code
                        for t in transcript_list
                        if t.is_generated
                    ]
                    seen: set = set()
                    languages = [
                        code
                        for code in default_variants + manual + generated + ["en", "en-US"]
                        if code and not (code in seen or seen.add(code))
                    ]

                def _extract_snippets(snippets):
                    parts = []
                    for item in snippets:
                        if hasattr(item, "text"):
                            parts.append(getattr(item, "text"))
                        elif isinstance(item, dict) and "text" in item:
                            parts.append(item["text"])
                        else:
                            parts.append(str(item))
                    return " ".join(parts)

                if languages:
                    try:
                        transcript = ytt_api.fetch(video_id, languages=languages)
                        if transcript:
                            transcript_text = _extract_snippets(transcript)
                    except Exception:
                        try:
                            transcript = (
                                transcript_list.find_transcript(languages)
                                .translate(languages[0])
                                .fetch()
                            )
                            transcript_text = _extract_snippets(transcript)
                        except Exception:
                            pass
            except Exception as e:
                print(f"YouTubeTranscriptApi failed: {e}")

        # Fallback to direct speech-to-text audio stream transcription if transcript_text is still empty
        if not transcript_text and url:
            try:
                transcript_text = self._transcribe_video_audio(url)
            except Exception as e:
                print(f"Audio transcription fallback error: {e}")

        if transcript_text:
            webpage_text += f"### Spoken Transcript\n{transcript_text}\n\n"

        return DocumentConverterResult(
            markdown=webpage_text.strip() + "\n",
            title=title,
        )

    def _get(
        self,
        metadata: Dict[str, str],
        keys: List[str],
        default: Union[str, None] = None,
    ) -> Union[str, None]:
        """Get first non-empty value from metadata matching given keys."""
        for k in keys:
            if k in metadata:
                return metadata[k]
        return default

    def _extract_video_id(self, url: Union[str, None]) -> Union[str, None]:
        """Extract an 11-character YouTube video id from the common URL forms:
        watch?v=..., youtu.be/..., /shorts/..., and /embed/..."""
        if not url:
            return None
        parsed = urlparse(url)
        v = parse_qs(parsed.query).get("v", [None])[0]
        if v:
            return v
        match = re.search(r"/(?:shorts|embed)/([A-Za-z0-9_-]{11})", parsed.path)
        if match:
            return match.group(1)
        if parsed.netloc.endswith("youtu.be"):
            candidate = parsed.path.lstrip("/").split("/")[0]
            if candidate:
                return candidate
        return None

    def _findKey(self, json: Any, key: str) -> Union[str, None]:  # TODO: Fix json type
        """Recursively search for a key in nested dictionary/list structures."""
        if isinstance(json, list):
            for elm in json:
                ret = self._findKey(elm, key)
                if ret is not None:
                    return ret
        elif isinstance(json, dict):
            for k, v in json.items():
                if k == key:
                    return json[k]
                if result := self._findKey(v, key):
                    return result
        return None

    def _retry_operation(self, operation, retries=3, delay=2):
        """Retries the operation if it fails."""
        attempt = 0
        while attempt < retries:
            try:
                return operation()  # Attempt the operation
            except Exception as e:
                print(f"Attempt {attempt + 1} failed: {e}")
                if attempt < retries - 1:
                    time.sleep(delay)  # Wait before retrying
                attempt += 1
        # If all attempts fail, raise the last exception
        raise Exception(f"Operation failed after {retries} attempts.")

    def _fetch_innertube_details(self, video_id: str) -> Dict[str, Any]:
        """Fetch full video description, chapters, and details via official Innertube API."""
        import json
        import urllib.request

        url = "https://www.youtube.com/youtubei/v1/next"
        payload = {
            "videoId": video_id,
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20240312.01.00",
                    "hl": "en",
                    "gl": "US"
                }
            }
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                descriptions = []
                contents = data.get("contents", {}).get("twoColumnWatchNextResults", {}).get("results", {}).get("results", {}).get("contents", [])
                for c in contents:
                    for k, v in c.items():
                        if "videoSecondaryInfoRenderer" in k or "videoPrimaryInfoRenderer" in k:
                            def search_text(obj):
                                texts = []
                                if isinstance(obj, dict):
                                    if "content" in obj and isinstance(obj["content"], str) and len(obj["content"]) > 10:
                                        texts.append(obj["content"])
                                    if "simpleText" in obj and isinstance(obj["simpleText"], str) and len(obj["simpleText"]) > 10:
                                        texts.append(obj["simpleText"])
                                    for sub in obj.values():
                                        texts.extend(search_text(sub))
                                elif isinstance(obj, list):
                                    for item in obj:
                                        texts.extend(search_text(item))
                                return texts

                            found = search_text(v)
                            for f in found:
                                if len(f) > 50 and ("http" in f or "0:" in f or "\n" in f or "video" in f or "Aura" in f):
                                    descriptions.append(f)

                description_text = max(descriptions, key=len) if descriptions else ""
                return {"description": description_text}
        except Exception as e:
            print(f"Error fetching Innertube video details: {e}")
            return {}

    def _transcribe_video_audio(self, url: str) -> str:
        """Fallback to speech-to-text audio stream transcription if caption tracks are blocked."""
        try:
            from pytubefix import YouTube
            import urllib.request
            import speech_recognition as sr
            import pydub
            import io

            yt = YouTube(url)
            audio_stream = yt.streams.get_audio_only()
            if not audio_stream:
                return ""

            req = urllib.request.Request(
                audio_stream.url,
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
            )
            with urllib.request.urlopen(req, timeout=6) as resp:
                raw = resp.read(1024 * 1024 * 1)  # Fetch 1MB audio stream (~1 min speech, ultra-fast response)

            audio_seg = pydub.AudioSegment.from_file(io.BytesIO(raw), format="m4a")
            wav_io = io.BytesIO()
            audio_seg.export(wav_io, format="wav")
            wav_io.seek(0)

            rec = sr.Recognizer()
            with sr.AudioFile(wav_io) as source:
                audio_data = rec.record(source)
                return rec.recognize_google(audio_data).strip()
        except Exception as e:
            print(f"Error in _transcribe_video_audio: {e}")
            return ""
