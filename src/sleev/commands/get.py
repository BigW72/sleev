"""sleev get — download missing cover art into album folders.

Treats a folder holding audio files as an album, identifies it from tags
(falling back to the folder name), then saves the front cover from the Cover
Art Archive alongside the audio. Audio files are not modified.

Only PATH itself is scanned unless `--recurse` is given, which walks the whole
tree and treats every folder holding audio files as an album.

A folder that already has a cover is skipped, unless that cover is too small to
be worth keeping (see `--min-size`) or `--overwrite` is given. `--normalise`
makes every cover the folder ends up with a PNG named after `--name`, whether
it was downloaded or already on disk.
"""

import argparse
import logging
from pathlib import Path

from sleev.images import MIN_COVER_PIXELS, data_to_png, dimensions, to_png
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
        "--min-size",
        type=int,
        default=MIN_COVER_PIXELS,
        metavar="PX",
        help=(
            "existing covers smaller than this on either side are replaced "
            "rather than kept (default: %(default)s)"
        ),
    )
    parser.add_argument(
        "--normalise",
        "--normalize",
        action="store_true",
        help="write every cover as STEM.png, converting downloads and existing art alike",
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


def keep_floor(args: argparse.Namespace) -> int:
    """The size an existing cover must reach to be worth keeping.

    Normally --min-size, but never more than the art we would download to
    replace it: fetching at --size 250 must not throw away a 400px cover.
    """
    if args.size == "original":
        return args.min_size
    return min(args.min_size, int(args.size))


def keep(existing: Path, album: Album, args: argparse.Namespace) -> str:
    """Handle a cover we've decided is good enough, normalising it if asked."""
    destination = album.path / f"{args.name}.png"
    if not args.normalise or existing == destination:
        log.info("skip   %s (has %s)", album.label, existing.name)
        return "skipped"

    if args.dry_run:
        log.info("would  %s: %s -> %s", album.label, existing.name, destination.name)
        return "would-normalise"

    try:
        to_png(existing, destination)
    except OSError as exc:
        log.error("error  %s: could not convert %s: %s", album.label, existing.name, exc)
        return "failed"

    log.info("conv   %s: %s -> %s", album.label, existing.name, destination.name)
    return "normalised"


def process(album: Album, client: CoverArtClient, args: argparse.Namespace) -> str:
    """Fetch and save art for one album. Returns a one-word outcome."""
    existing = has_cover(album.path)
    if existing and not args.overwrite:
        size = dimensions(existing)
        if size is None:
            log.debug("%s is not a readable image, replacing it", existing)
        elif min(size) >= keep_floor(args):
            return keep(existing, album, args)
        else:
            log.debug("%s is %dx%d, replacing it", existing, *size)

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

    if args.normalise:
        destination = album.path / f"{args.name}.png"
        try:
            data_to_png(cover.data, destination)
        except OSError as exc:
            log.error("error  %s: downloaded art wasn't a usable image: %s", album.label, exc)
            return "failed"
    else:
        destination = album.path / f"{args.name}{cover.extension}"
        destination.write_bytes(cover.data)

    if existing and existing != destination:
        # Otherwise the folder keeps both, and players may prefer the old one.
        existing.unlink()
        log.info("saved  %s -> %s (replaced %s)", album.label, destination.name, existing.name)
        return "replaced"

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
