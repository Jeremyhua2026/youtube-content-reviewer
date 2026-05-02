import json
import os
import time
from threading import Lock
from typing import Optional

_LOCK = Lock()
_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "library_data.json",
)


def _ensure() -> None:
    if not os.path.exists(_DATA_PATH):
        with open(_DATA_PATH, "w", encoding="utf-8") as f:
            json.dump({"videos": []}, f, indent=2)


def _read() -> dict:
    _ensure()
    with open(_DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "videos" not in data or not isinstance(data["videos"], list):
        data = {"videos": []}
    return data


def _write(data: dict) -> None:
    with open(_DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_all(sort: str = "rating", q: str = "", tag: str = "") -> list:
    with _LOCK:
        data = _read()
        videos = list(data["videos"])

    if q:
        ql = q.lower().strip()
        def matches(v):
            haystack = " ".join([
                v.get("title", ""),
                v.get("creator", ""),
                v.get("notes", ""),
                " ".join(v.get("tags", []) or []),
                (v.get("analysis", {}) or {}).get("summary", ""),
                (v.get("analysis", {}) or {}).get("creator_notes", ""),
                (v.get("analysis", {}) or {}).get("personal_relevance", ""),
                " ".join((v.get("analysis", {}) or {}).get("key_insights", []) or []),
            ]).lower()
            return ql in haystack
        videos = [v for v in videos if matches(v)]

    if tag:
        tl = tag.lower().strip()
        videos = [v for v in videos if tl in [t.lower() for t in (v.get("tags") or [])]]

    if sort == "rating":
        videos.sort(key=lambda v: (v.get("rating") or 0, v.get("updated_at") or 0), reverse=True)
    elif sort == "recent":
        videos.sort(key=lambda v: v.get("updated_at") or 0, reverse=True)
    elif sort == "creator":
        videos.sort(key=lambda v: (v.get("creator") or "").lower())
    return videos


def stats() -> dict:
    with _LOCK:
        videos = list(_read()["videos"])
    total = len(videos)
    rated = [v for v in videos if v.get("rating") not in (None, 0)]
    avg = round(sum(v["rating"] for v in rated) / len(rated), 1) if rated else None
    top = max(rated, key=lambda v: v.get("rating") or 0) if rated else None

    creator_counts = {}
    tag_counts = {}
    for v in videos:
        c = v.get("creator") or ""
        if c:
            creator_counts[c] = creator_counts.get(c, 0) + 1
        for t in (v.get("tags") or []):
            tag_counts[t] = tag_counts.get(t, 0) + 1
    top_creator = max(creator_counts.items(), key=lambda kv: kv[1])[0] if creator_counts else None
    top_tag = max(tag_counts.items(), key=lambda kv: kv[1])[0] if tag_counts else None

    return {
        "total": total,
        "rated_count": len(rated),
        "avg_rating": avg,
        "top_video": {"title": top.get("title"), "video_id": top.get("video_id"), "rating": top.get("rating")} if top else None,
        "top_creator": top_creator,
        "top_tag": top_tag,
        "all_tags": sorted(tag_counts.keys(), key=lambda t: -tag_counts[t]),
    }


def highlights(limit: int = 8) -> list:
    """Return top key_insights pulled from the highest-rated videos."""
    with _LOCK:
        videos = list(_read()["videos"])
    videos.sort(key=lambda v: v.get("rating") or 0, reverse=True)
    out = []
    for v in videos:
        insights = (v.get("analysis", {}) or {}).get("key_insights") or []
        for ins in insights[:2]:
            out.append({
                "insight": ins,
                "video_id": v.get("video_id"),
                "title": v.get("title"),
                "creator": v.get("creator"),
                "rating": v.get("rating"),
            })
            if len(out) >= limit:
                return out
    return out


def get(video_id: str) -> Optional[dict]:
    with _LOCK:
        for v in _read()["videos"]:
            if v.get("video_id") == video_id:
                return v
    return None


def upsert_analysis(analysis: dict) -> dict:
    """Insert or update an entry from a fresh /analyze result.
    Preserves user-set rating and notes if they already exist."""
    vid = analysis.get("video_id")
    if not vid:
        raise ValueError("analysis missing video_id")
    now = int(time.time())
    with _LOCK:
        data = _read()
        existing = next((v for v in data["videos"] if v.get("video_id") == vid), None)
        if existing:
            existing.update({
                "video_id": vid,
                "title": analysis.get("video_title") or existing.get("title", ""),
                "creator": analysis.get("video_creator") or existing.get("creator", ""),
                "thumbnail": analysis.get("video_thumbnail") or existing.get("thumbnail", ""),
                "analysis": {
                    "summary": analysis.get("summary", ""),
                    "creator_notes": analysis.get("creator_notes", ""),
                    "key_insights": analysis.get("key_insights", []),
                    "personal_relevance": analysis.get("personal_relevance", ""),
                    "delivery_script": analysis.get("delivery_script", {}),
                },
                "updated_at": now,
            })
            entry = existing
        else:
            entry = {
                "video_id": vid,
                "title": analysis.get("video_title", ""),
                "creator": analysis.get("video_creator", ""),
                "thumbnail": analysis.get("video_thumbnail", ""),
                "analysis": {
                    "summary": analysis.get("summary", ""),
                    "creator_notes": analysis.get("creator_notes", ""),
                    "key_insights": analysis.get("key_insights", []),
                    "personal_relevance": analysis.get("personal_relevance", ""),
                    "delivery_script": analysis.get("delivery_script", {}),
                },
                "rating": None,
                "notes": "",
                "tags": [t.lower().strip() for t in (analysis.get("suggested_tags") or []) if t],
                "created_at": now,
                "updated_at": now,
            }
            data["videos"].append(entry)
        _write(data)
    return entry


def update(video_id: str, rating: Optional[float] = None, notes: Optional[str] = None, tags: Optional[list] = None) -> Optional[dict]:
    now = int(time.time())
    with _LOCK:
        data = _read()
        for v in data["videos"]:
            if v.get("video_id") == video_id:
                if rating is not None:
                    try:
                        r = float(rating)
                        if r < 0: r = 0
                        if r > 10: r = 10
                        v["rating"] = r
                    except (TypeError, ValueError):
                        pass
                if notes is not None:
                    v["notes"] = str(notes)
                if tags is not None:
                    cleaned = []
                    seen = set()
                    for t in tags:
                        s = str(t).strip().lower()
                        if s and s not in seen:
                            cleaned.append(s)
                            seen.add(s)
                    v["tags"] = cleaned
                v["updated_at"] = now
                _write(data)
                return v
    return None


def delete(video_id: str) -> bool:
    with _LOCK:
        data = _read()
        before = len(data["videos"])
        data["videos"] = [v for v in data["videos"] if v.get("video_id") != video_id]
        if len(data["videos"]) != before:
            _write(data)
            return True
    return False
