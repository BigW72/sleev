"""Find album folders on disk and work out what album each one holds."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import os
from pathlib import Path
import re

import mutagen

AUDIO_EXTENSIONS = frozenset(
    {".mp3", ".flac", ".m4a", ".m4b", ".mp4", ".ogg", ".oga", ".opus", ".wma", ".wav", ".aiff", ".ape", ".wv"}
)

# Files that count as a folder's cover art. Both lists are in preference order:
# a folder holding cover.png and folder.jpg yields the former, so repeated runs
# pick the same file rather than whichever the filesystem listed first.
COVER_STEMS = ("cover", "folder", "front", "album", "albumart", "albumartsmall")
COVER_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

# Tag keys are checked in order; the first one present wins.
ARTIST_KEYS = ("albumartist", "album artist", "artist", "performer")
ALBUM_KEYS = ("album",)

# How many audio files to read per folder before deciding on artist/album.
MAX_FILES_SAMPLED = 12

_YEAR = r"(?:19|20)\d{2}"
_DASH = r"\s+-{1,2}\s+"

# Patterns are tried in this order; the first match wins. Order matters more
# than it looks: "Dr. Dre - 1999 - 2001" is an album actually called "2001",
# and "A Clockwork Orange (OST) - 1972" would otherwise parse as an artist
# named after the film with an album called "1972".
#
# "Artist - 1979 - Album", the dominant layout in folder-named libraries.
_FOLDER_ARTIST_YEAR_ALBUM = re.compile(rf"^(?P<artist>.+?){_DASH}{_YEAR}{_DASH}(?P<album>.+)$")
# "A Clockwork Orange (OST) - 1972" — soundtracks and compilations, no artist.
_FOLDER_ALBUM_YEAR = re.compile(rf"^(?P<album>.+?){_DASH}{_YEAR}$")
# "Artist - Album", "Artist -- Album [FLAC]"
_FOLDER_ARTIST_ALBUM = re.compile(r"^(?P<artist>.+?)\s+-{1,2}\s+(?P<album>.+)$")

_TRAILING_NOISE = re.compile(r"\s*[\(\[\{][^\)\]\}]*[\)\]\}]\s*$")


@dataclass(frozen=True)
class Album:
    """An album folder we might be able to fetch cover art for."""

    path: Path
    artist: str | None
    album: str | None
    source: str  # "tags", "folder", or "unknown"

    @property
    def label(self) -> str:
        if self.artist and self.album:
            return f"{self.artist} - {self.album}"
        return self.album or self.artist or self.path.name


def has_cover(folder: Path) -> Path | None:
    """Return the best existing cover image in *folder*, if there is one."""
    found: dict[tuple[str, str], Path] = {}
    for entry in folder.iterdir():
        if entry.is_file():
            found.setdefault((entry.stem.lower(), entry.suffix.lower()), entry)

    for stem in COVER_STEMS:
        for extension in COVER_EXTENSIONS:
            if match := found.get((stem, extension)):
                return match
    return None


def _audio_files(folder: Path) -> list[Path]:
    return sorted(
        entry
        for entry in folder.iterdir()
        if entry.is_file() and entry.suffix.lower() in AUDIO_EXTENSIONS
    )


def _first_tag(tags: mutagen.Tags, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = tags.get(key)
        if not value:
            continue
        # EasyMP3/EasyID3 give lists; other formats can give a bare string.
        text = value[0] if isinstance(value, list) else value
        text = str(text).strip()
        if text:
            return text
    return None


def _read_tags(files: list[Path]) -> tuple[str | None, str | None]:
    """Read artist/album from a sample of *files*, taking the most common value."""
    artists: Counter[str] = Counter()
    albums: Counter[str] = Counter()

    for path in files[:MAX_FILES_SAMPLED]:
        try:
            audio = mutagen.File(path, easy=True)
        except Exception:
            # A corrupt or truncated file shouldn't abort the whole scan.
            continue
        if audio is None or audio.tags is None:
            continue
        if artist := _first_tag(audio.tags, ARTIST_KEYS):
            artists[artist] += 1
        if album := _first_tag(audio.tags, ALBUM_KEYS):
            albums[album] += 1

    artist = artists.most_common(1)[0][0] if artists else None
    album = albums.most_common(1)[0][0] if albums else None
    return artist, album


def strip_qualifiers(album: str) -> str:
    """Drop trailing "(Deluxe)"-style qualifiers from an album title.

    Tags stack these — "The Annual 2009 (Disc 2) (Mixed by Goodwill) [AU]" —
    so this strips repeatedly. A title that is nothing but a qualifier is left
    alone rather than reduced to an empty string.
    """
    title = album.strip()
    while True:
        shorter = _TRAILING_NOISE.sub("", title).strip()
        if shorter == title or not shorter:
            return title
        title = shorter


def _drop_noise(title: str) -> str:
    """Strip a trailing "[FLAC]"-style tag, unless it is the whole title.

    Sigur Rós really did call an album "( )", so a title that is nothing but
    a bracketed group is left alone rather than erased.
    """
    stripped = _TRAILING_NOISE.sub("", title).strip()
    return stripped or title.strip()


def parse_folder_name(name: str) -> tuple[str | None, str | None]:
    """Best-effort split of a folder name into (artist, album)."""
    name = name.strip()

    # Matched against the raw name: stripping noise first would remove the
    # very brackets a title like "( )" consists of.
    if match := _FOLDER_ARTIST_YEAR_ALBUM.match(name):
        artist = match["artist"].strip()
    elif match := _FOLDER_ALBUM_YEAR.match(name):
        artist = ""
    elif match := _FOLDER_ARTIST_ALBUM.match(name):
        artist = match["artist"].strip()
    else:
        return None, (_drop_noise(name) or None)

    return (artist or None), (_drop_noise(match["album"]) or None)


def describe_folder(folder: Path) -> Album:
    """Work out which album *folder* holds, preferring tags over the folder name."""
    artist, album = _read_tags(_audio_files(folder))
    if artist and album:
        return Album(folder, artist, album, "tags")

    folder_artist, folder_album = parse_folder_name(folder.name)
    merged_artist = artist or folder_artist
    merged_album = album or folder_album
    if merged_artist or merged_album:
        source = "tags" if (artist or album) else "folder"
        return Album(folder, merged_artist, merged_album, source)

    return Album(folder, None, None, "unknown")


def find_album_folders(root: Path, *, recurse: bool = False) -> list[Album]:
    """Album folders at *root*.

    By default only *root* itself is considered, and it counts as an album
    folder if it directly contains audio files. With *recurse*, every folder
    in the tree that directly contains audio files is returned.
    """
    if not recurse:
        return [describe_folder(root)] if _audio_files(root) else []

    albums: list[Album] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if any(Path(f).suffix.lower() in AUDIO_EXTENSIONS for f in filenames):
            albums.append(describe_folder(Path(dirpath)))
    return albums


def find_cover_folders(root: Path, *, recurse: bool = False) -> list[Path]:
    """Folders at *root* that hold a cover image, whether or not they hold audio.

    Unlike `find_album_folders` this doesn't care about audio: an artist folder
    or a film folder with its own artwork counts too.
    """
    if not recurse:
        return [root] if has_cover(root) else []

    folders: list[Path] = []
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        folder = Path(dirpath)
        if has_cover(folder):
            folders.append(folder)
    return folders
