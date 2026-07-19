"""sleev get — download missing cover art into album folders.

Treats a folder holding audio files as an album, identifies it from tags
(falling back to the folder name), then saves the front cover from the Cover
Art Archive alongside the audio. Audio files are not modified.

Only PATH itself is scanned unless `--recurse` is given, which walks the whole
tree and treats every folder holding audio files as an album.

Folders that already have a cover are skipped unless `--overwrite` is given.
"""

import argparse
import logging
from pathlib import Path

from sleev.musicbrainz import SIZES, CoverArtClient, CoverArtError
from sleev.scan import Album, find_album_folders, has_cover

log = logging.getLogger(__name__)


# ── command registration ─────────────────────────────────────────────────────


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "get",
        help="download missing cover art from the Cover Art Archive",
        description=(
            "Download PATH's front cover from the Cover Art Archive, or with "
            "--recurse, that of every album folder beneath it. Albums are "
            "identified from audio tags where possible, otherwise from the "
            "folder name. MusicBrainz limits lookups to one per second, so "
            "expect roughly two seconds per album."
        ),
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        type=Path,
        metavar="PATH",
        help="folder to scan (default: current directory)",
    )
    parser.add_argument(
        "-r",
        "--recurse",
        action="store_true",
        help="also scan subfolders, not just PATH itself",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="report what would happen, download nothing",
    )
    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="replace covers that already exist",
    )
    parser.add_argument(
        "-s",
        "--size",
        choices=SIZES,
        default="500",
        help="image size to fetch (default: %(default)s)",
    )
    parser.add_argument(
        "--name",
        default="cover",
        metavar="STEM",
        help="filename stem to write; extension follows the image type (default: %(default)s)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        metavar="N",
        help="MusicBrainz candidates to try per album (default: %(default)s)",
    )
    parser.set_defaults(func=run)


# ── implementation ───────────────────────────────────────────────────────────


def process(album: Album, client: CoverArtClient, args: argparse.Namespace) -> str:
    """Fetch and save art for one album. Returns a one-word outcome."""
    existing = has_cover(album.path)
    if existing and not args.overwrite:
        log.info("skip   %s (has %s)", album.label, existing.name)
        return "skipped"

    if not album.album:
        log.warning("no id  %s (no album name in tags or folder name)", album.path)
        return "unidentified"

    if args.dry_run:
        log.info("would  %s [%s]", album.label, album.source)
        return "would-fetch"

    try:
        cover = client.find_cover(album.artist, album.album, size=args.size, limit=args.limit)
    except CoverArtError as exc:
        log.error("error  %s: %s", album.label, exc)
        return "failed"

    if cover is None:
        log.warning("miss   %s (no art found)", album.label)
        return "not-found"

    destination = album.path / f"{args.name}{cover.extension}"
    destination.write_bytes(cover.data)
    log.info("saved  %s -> %s", album.label, destination.name)
    return "saved"


def run(args: argparse.Namespace) -> int:
    root = args.root.expanduser().resolve()
    if not root.is_dir():
        log.error("%s is not a directory", root)
        return 2

    albums = find_album_folders(root, recurse=args.recurse)
    if not albums:
        if args.recurse:
            log.error("no folders containing audio files under %s", root)
        else:
            log.error("%s contains no audio files (use --recurse to scan subfolders)", root)
        return 1
    log.info("found %d album folder(s) under %s\n", len(albums), root)

    counts: dict[str, int] = {}
    with CoverArtClient() as client:
        for album in albums:
            outcome = process(album, client, args)
            counts[outcome] = counts.get(outcome, 0) + 1

    log.info("\n%s", ", ".join(f"{count} {name}" for name, count in sorted(counts.items())))
    return 0 if not counts.get("failed") else 1
