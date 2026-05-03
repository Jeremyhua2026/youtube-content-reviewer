import json
import os
import re
import urllib.request
import urllib.parse as _urlparse
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi

# Optional residential proxy (needed when running on cloud hosts like Render —
# YouTube blocks most cloud-provider IPs from transcript endpoints).
# If WEBSHARE_PROXY_USERNAME and WEBSHARE_PROXY_PASSWORD env vars are set,
# we route through Webshare's residential pool. Otherwise we go direct.
_PROXY_CONFIG = None
try:
    from youtube_transcript_api.proxies import WebshareProxyConfig, GenericProxyConfig
    _ws_user = os.environ.get("WEBSHARE_PROXY_USERNAME", "").strip()
    _ws_pass = os.environ.get("WEBSHARE_PROXY_PASSWORD", "").strip()
    _http_proxy = os.environ.get("HTTP_PROXY_URL", "").strip()
    if _ws_user and _ws_pass:
        _PROXY_CONFIG = WebshareProxyConfig(proxy_username=_ws_user, proxy_password=_ws_pass)
    elif _http_proxy:
        _PROXY_CONFIG = GenericProxyConfig(http_url=_http_proxy, https_url=_http_proxy)
except Exception:
    _PROXY_CONFIG = None
from youtube_transcript_api._errors import (
    TranscriptsDisabled,
    NoTranscriptFound,
    VideoUnavailable,
)


class TranscriptError(Exception):
    pass


def extract_video_id(url_or_id: str) -> str:
    s = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s

    parsed = urlparse(s)
    host = (parsed.hostname or "").lower()

    if host in ("youtu.be",):
        vid = parsed.path.lstrip("/").split("/")[0]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return vid

    if "youtube.com" in host or "youtube-nocookie.com" in host:
        qs = parse_qs(parsed.query)
        if "v" in qs and re.fullmatch(r"[A-Za-z0-9_-]{11}", qs["v"][0]):
            return qs["v"][0]
        m = re.match(r"^/(embed|shorts|live)/([A-Za-z0-9_-]{11})", parsed.path)
        if m:
            return m.group(2)

    m = re.search(r"([A-Za-z0-9_-]{11})", s)
    if m:
        return m.group(1)

    raise TranscriptError(f"Could not extract video ID from: {url_or_id}")


def _entries_to_text(entries) -> str:
    parts = []
    for e in entries:
        # Support both old dict format and new snippet objects
        t = e.get("text") if isinstance(e, dict) else getattr(e, "text", "")
        if t:
            parts.append(t.strip())
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def fetch_transcript(url_or_id: str) -> dict:
    video_id = extract_video_id(url_or_id)
    try:
        # youtube-transcript-api >= 1.0 uses an instance .fetch() method.
        # Older versions exposed a class method .get_transcript().
        if hasattr(YouTubeTranscriptApi, "get_transcript") and _PROXY_CONFIG is None:
            entries = YouTubeTranscriptApi.get_transcript(video_id)
        else:
            api = YouTubeTranscriptApi(proxy_config=_PROXY_CONFIG) if _PROXY_CONFIG else YouTubeTranscriptApi()
            fetched = api.fetch(video_id)
            # FetchedTranscript is iterable of FetchedTranscriptSnippet (has .text)
            entries = list(fetched)
    except TranscriptsDisabled:
        raise TranscriptError("Transcripts are disabled for this video.")
    except NoTranscriptFound:
        raise TranscriptError("No transcript found for this video.")
    except VideoUnavailable:
        raise TranscriptError("Video is unavailable or private.")
    except Exception as e:
        raise TranscriptError(f"Failed to fetch transcript: {e}")

    text = _entries_to_text(entries)
    if not text:
        raise TranscriptError("Transcript was empty.")

    meta = fetch_metadata(video_id)
    return {"video_id": video_id, "transcript": text, **meta}


def fetch_metadata(video_id: str) -> dict:
    """Fetch title + channel name via YouTube's free oEmbed endpoint (no API key)."""
    out = {"title": "", "creator": "", "thumbnail": ""}
    try:
        url = "https://www.youtube.com/watch?v=" + video_id
        oembed = "https://www.youtube.com/oembed?" + _urlparse.urlencode(
            {"url": url, "format": "json"}
        )
        req = urllib.request.Request(oembed, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out["title"] = (data.get("title") or "").strip()
        out["creator"] = (data.get("author_name") or "").strip()
        out["thumbnail"] = (data.get("thumbnail_url") or "").strip()
    except Exception:
        pass
    return out
