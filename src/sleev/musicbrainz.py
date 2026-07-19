"""Look up releases on MusicBrainz and pull their art from the Cover Art Archive."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time

import httpx

log = logging.getLogger(__name__)

MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/release-group"
COVER_ART_URL = "https://coverartarchive.org/release-group"

# MusicBrainz asks for one request per second and a User-Agent that identifies the app.
MIN_REQUEST_INTERVAL = 1.0
USER_AGENT = "sleev/0.1.0 ( https://github.com/BigW72/sleev )"

# CAA serves these thumbnail sizes; "original" is the unresized upload.
SIZES = ("250", "500", "1200", "original")

CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class CoverArtError(RuntimeError):
    """A lookup failed in a way worth reporting but not worth stopping the run for."""


@dataclass(frozen=True)
class Candidate:
    """A MusicBrainz release group that might be the album we're looking at."""

    mbid: str
    title: str
    artist: str
    score: int


@dataclass(frozen=True)
class Cover:
    """Downloaded artwork."""

    data: bytes
    extension: str
    mbid: str


def _escape(term: str) -> str:
    """Escape Lucene syntax so punctuation in album titles doesn't break the query."""
    out = []
    for char in term:
        if char in r'+-&|!(){}[]^"~*?:\/':
            out.append("\\")
        out.append(char)
    return "".join(out)


class CoverArtClient:
    """A rate-limited MusicBrainz + Cover Art Archive client."""

    def __init__(self, *, timeout: float = 20.0, user_agent: str = USER_AGENT) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent},
        )
        self._last_request = 0.0

    def __enter__(self) -> CoverArtClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < MIN_REQUEST_INTERVAL:
            time.sleep(MIN_REQUEST_INTERVAL - elapsed)
        self._last_request = time.monotonic()

    def search(self, artist: str | None, album: str | None, *, limit: int = 5) -> list[Candidate]:
        """Find release groups matching *artist* and *album*, best match first."""
        if not album:
            return []

        terms = [f'releasegroup:"{_escape(album)}"']
        if artist:
            terms.append(f'artist:"{_escape(artist)}"')
        params = {"query": " AND ".join(terms), "fmt": "json", "limit": str(limit)}

        self._throttle()
        try:
            response = self._client.get(MUSICBRAINZ_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CoverArtError(f"MusicBrainz lookup failed: {exc}") from exc

        candidates = []
        for group in response.json().get("release-groups", []):
            credits = group.get("artist-credit") or []
            names = "".join(
                f"{c.get('name', '')}{c.get('joinphrase', '')}" for c in credits
            ).strip()
            candidates.append(
                Candidate(
                    mbid=group["id"],
                    title=group.get("title", ""),
                    artist=names,
                    score=int(group.get("score", 0)),
                )
            )
        return candidates

    def fetch_front(self, mbid: str, size: str = "500") -> Cover | None:
        """Download the front cover for a release group, or None if there isn't one."""
        suffix = "" if size == "original" else f"-{size}"
        url = f"{COVER_ART_URL}/{mbid}/front{suffix}"

        self._throttle()
        try:
            response = self._client.get(url)
        except httpx.HTTPError as exc:
            raise CoverArtError(f"Cover Art Archive request failed: {exc}") from exc

        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        if response.is_error:
            raise CoverArtError(f"Cover Art Archive returned {response.status_code} for {mbid}")

        content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
        extension = CONTENT_TYPE_EXTENSIONS.get(content_type, ".jpg")
        return Cover(data=response.content, extension=extension, mbid=mbid)

    def find_cover(
        self, artist: str | None, album: str | None, *, size: str = "500", limit: int = 5
    ) -> Cover | None:
        """Search for the album, then return art from the first candidate that has any."""
        for candidate in self.search(artist, album, limit=limit):
            log.debug("trying %s - %s (%s)", candidate.artist, candidate.title, candidate.mbid)
            if cover := self.fetch_front(candidate.mbid, size=size):
                return cover
        return None
