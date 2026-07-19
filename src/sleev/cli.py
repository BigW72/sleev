"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from .musicbrainz import SIZES, CoverArtClient, CoverArtError
from .scan import Album, find_album_folders, has_cover

log = logging.getLogger("sleev")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sleev",
        description="Fetch album cover art from the Cover Art Archive into album folders.",
    )
    parser.add_argument(
        "root", nargs="?", default=".", type=Path, help="folder to scan (default: current)"
    )
    parser.add_argument(
        "-n", "--dry-run", action="store_true", help="report what would happen, download nothing"
    )
    parser.add_argument(
        "-f", "--overwrite", action="store_true", help="replace covers that already exist"
    )
    parser.add_argument(
        "-s", "--size", choices=SIZES, default="500", help="image size to fetch (default: 500)"
    )
    parser.add_argument("--name", default="cover", help="filename stem to write (default: cover)")
    parser.add_argument(
        "--limit", type=int, default=5, help="MusicBrainz candidates to try per album (default: 5)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show per-request detail")
    return parser


def _target_path(album: Album, stem: str, extension: str) -> Path:
    return album.path / f"{stem}{extension}"


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

    destination = _target_path(album, args.name, cover.extension)
    destination.write_bytes(cover.data)
    log.info("saved  %s -> %s", album.label, destination.name)
    return "saved"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    log.setLevel(logging.DEBUG if args.verbose else logging.INFO)
    # httpx/httpcore log every socket operation at DEBUG, which buries our own output.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        log.error("%s is not a directory", root)
        return 2

    albums = find_album_folders(root)
    if not albums:
        log.error("no folders containing audio files under %s", root)
        return 1
    log.info("found %d album folder(s) under %s\n", len(albums), root)

    counts: dict[str, int] = {}
    with CoverArtClient() as client:
        for album in albums:
            outcome = process(album, client, args)
            counts[outcome] = counts.get(outcome, 0) + 1

    log.info("\n%s", ", ".join(f"{count} {name}" for name, count in sorted(counts.items())))
    return 0 if not counts.get("failed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
