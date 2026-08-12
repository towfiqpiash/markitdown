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

        if not url.startswith("https://www.youtube.com/watch?"):
            # Not a YouTube URL
            return False

        if extension in ACCEPTED_FILE_EXTENSIONS:
            return True

        for prefix in ACCEPTED_MIME_TYPE_PREFIXES:
            if mimetype.startswith(prefix):
                return True

        # Not HTML content
        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: StreamInfo,
        **kwargs: Any,  # Options to pass to the converter
    ) -> DocumentConverterResult:
        # Parse the stream
        encoding = "utf-8" if stream_info.charset is None else stream_info.charset
        soup = bs4.BeautifulSoup(file_stream, "html.parser", from_encoding=encoding)

        # Read the meta tags
        metadata: Dict[str, str] = {}

        if soup.title and soup.title.string:
            metadata["title"] = soup.title.string

        for meta in soup(["meta"]):
            if not isinstance(meta, bs4.Tag):
                continue

            for a in meta.attrs:
                if a in ["itemprop", "property", "name"]:
                    key = str(meta.get(a, ""))
                    content = str(meta.get("content", ""))
                    if key and content:  # Only add non-empty content
                        metadata[key] = content
                    break

        # Capture the video's original audio language (e.g. "bn" for a Bengali
        # video), when present, so the transcript can be fetched in that
        # language rather than defaulting to English.
        try:
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
            print(f"Error extracting default audio language: {e}")
            pass

        # Start preparing the page
        webpage_text = ""

        title = self._get(metadata, ["title", "og:title", "name"])  # type: ignore
        assert isinstance(title, str)

        if title:
            webpage_text += f"# {title}\n"

        if IS_YOUTUBE_TRANSCRIPT_CAPABLE:
            transcript_text = ""
            video_id = self._extract_video_id(stream_info.url)  # type: ignore
            if video_id:
                # A failure to obtain the transcript (captions disabled, the
                # video is age-restricted/unavailable, or YouTube is
                # rate-limiting/blocking the request) must not abort the whole
                # conversion -- the title, metadata, and description are still
                # useful on their own.
                try:
                    ytt_api = YouTubeTranscriptApi()
                    transcript_list = ytt_api.list(video_id)

                    # Decide which language to fetch. An explicit caller
                    # override wins; otherwise prefer the video's own language
                    # -- its default audio language (so a Bengali video yields a
                    # Bengali transcript), then manually-created captions, then
                    # auto-generated ones -- instead of defaulting to English.
                    languages = kwargs.get("youtube_transcript_languages")
                    if not languages:
                        default_lang = self._get(metadata, ["defaultAudioLanguage"])
                        default_variants = []
                        if default_lang:
                            # e.g. "en-US" -> prefer both "en-US" and "en".
                            default_variants = [default_lang, default_lang.split("-")[0]]
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
                        # De-duplicate while preserving priority order.
                        seen: set = set()
                        languages = [
                            code
                            for code in default_variants + manual + generated
                            if code and not (code in seen or seen.add(code))
                        ]

                    if languages:
                        try:
                            # Retry the transcript fetching operation
                            transcript = self._retry_operation(
                                lambda: ytt_api.fetch(video_id, languages=languages),
                                retries=3,  # Retry 3 times
                                delay=2,  # 2 seconds delay between retries
                            )
                            if transcript:
                                transcript_text = " ".join(
                                    [part.text for part in transcript]
                                )  # type: ignore
                        except Exception:
                            # Preferred languages unavailable -- translate an
                            # available transcript into the top preference.
                            transcript = (
                                transcript_list.find_transcript(languages)
                                .translate(languages[0])
                                .fetch()
                            )
                            transcript_text = " ".join(
                                [part.text for part in transcript]
                            )
                except Exception as e:
                    # No transcript could be retrieved -- skip it gracefully.
                    print(f"Error fetching transcript: {e}")
            if transcript_text:
                webpage_text += f"\n### Transcript\n{transcript_text}\n"

        title = title if title else (soup.title.string if soup.title else "")
        assert isinstance(title, str)

        return DocumentConverterResult(
            markdown=webpage_text,
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
