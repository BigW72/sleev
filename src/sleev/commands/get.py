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

from sleev.images import MIN_COVER_PIXELS, data_to_png_bytes, dimensions, png_bytes, to_png
from sleev.musicbrainz import SIZES, CoverArtClient, CoverArtError
from sleev.scan import Album, find_album_folders, has_cover, strip_qualifiers

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


def worth_keeping(cover: Path, args: argparse.Namespace) -> bool:
    """Is this existing cover big enough, and readable, to leave in place?"""
    size = dimensions(cover)
    if size is None:
        log.debug("%s is not a readable image, replacing it", cover)
        return False
    if min(size) >= keep_floor(args):
        return True
    log.debug("%s is %dx%d, replacing it", cover, *size)
    return False


def keep(usable: Path, album: Album, args: argparse.Namespace) -> str:
    """Spread art we already have across the album's folders.

    The parent of a box set often has the artwork while its discs have none,
    so a cover worth keeping is copied into whichever folders lack one. That
    also means such a box set never needs a lookup.
    """
    suffix = ".png" if args.normalise else usable.suffix
    filled, converted = [], []

    for folder in album.folders:
        destination = folder / f"{args.name}{suffix}"
        current = has_cover(folder)

        if current is not None and worth_keeping(current, args):
            # Already has art of its own; only the name and format may be off.
            if args.normalise and current != destination:
                converted.append((folder, current, destination))
            continue
        filled.append((folder, current, destination))

    if not filled and not converted:
        log.info("skip   %s (has %s)", album.label, usable.name)
        return "skipped"

    if args.dry_run:
        for folder, _current, destination in converted + filled:
            log.info("would  %s: %s -> %s", album.label, folder.name, destination.name)
        return "would-normalise" if converted and not filled else "would-fill"

    try:
        # Encode once, then write the same bytes everywhere.
        payload = png_bytes(usable) if args.normalise else usable.read_bytes()
        for _folder, current, destination in filled:
            destination.write_bytes(payload)
            if current is not None and current != destination:
                current.unlink()
        for _folder, current, destination in converted:
            to_png(current, destination)
    except OSError as exc:
        log.error("error  %s: could not place %s: %s", album.label, usable.name, exc)
        return "failed"

    if filled:
        log.info("fill   %s -> %d folder(s)", album.label, len(filled))
        return "filled"

    log.info("conv   %s: %s -> %s", album.label, usable.name, f"{args.name}.png")
    return "normalised"


def process(album: Album, client: CoverArtClient, args: argparse.Namespace) -> str:
    """Fetch and save art for one album. Returns a one-word outcome."""
    if not args.overwrite:
        # Any folder in the group with art worth keeping can supply the rest.
        for folder in album.folders:
            found = has_cover(folder)
            if found is not None and worth_keeping(found, args):
                return keep(found, album, args)

    if not album.album:
        log.warning("no id  %s (no album name in tags or folder name)", album.path)
        return "unidentified"

    if args.dry_run:
        log.info("would  %s [%s]", album.label, album.source)
        return "would-fetch"

    # Tags routinely carry an edition qualifier the archive doesn't know about,
    # so a miss on "Animals [1997 Remaster]" is worth retrying as "Animals".
    titles = [album.album]
    if (simpler := strip_qualifiers(album.album)) != album.album:
        titles.append(simpler)

    cover = None
    for title in titles:
        if title != album.album:
            log.debug("retrying %s as %r", album.label, title)
        try:
            cover = client.find_cover(album.artist, title, size=args.size, limit=args.limit)
        except CoverArtError as exc:
            log.error("error  %s: %s", album.label, exc)
            return "failed"
        if cover is not None:
            break

    if cover is None:
        log.warning("miss   %s (no art found)", album.label)
        return "not-found"

    try:
        payload = data_to_png_bytes(cover.data) if args.normalise else cover.data
    except OSError as exc:
        log.error("error  %s: downloaded art wasn't a usable image: %s", album.label, exc)
        return "failed"

    suffix = ".png" if args.normalise else cover.extension
    replaced = []
    for folder in album.folders:
        destination = folder / f"{args.name}{suffix}"
        current = has_cover(folder)
        destination.write_bytes(payload)
        if current is not None and current != destination:
            # Otherwise the folder keeps both, and players may prefer the old one.
            current.unlink()
            replaced.append(current)

    where = f"{args.name}{suffix}"
    if len(album.folders) > 1:
        log.info("saved  %s -> %s in %d folder(s)", album.label, where, len(album.folders))
    elif replaced:
        log.info("saved  %s -> %s (replaced %s)", album.label, where, replaced[0].name)
    else:
        log.info("saved  %s -> %s", album.label, where)

    return "replaced" if replaced else "saved"


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
