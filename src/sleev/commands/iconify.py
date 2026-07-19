"""sleev iconify — use each folder's cover art as its Finder icon.

Any folder holding a cover image qualifies, audio or not, so artist folders and
box sets get artwork alongside the albums themselves. Folders whose icon has
already been set are left alone unless `--force` is given.

macOS only: there is no cross-platform equivalent of the API this uses.
"""

import argparse
import logging
from pathlib import Path
import tempfile

from sleev.icons import IconError, has_custom_icon, is_supported, set_folder_icon
from sleev.images import to_icns
from sleev.scan import find_cover_folders, has_cover

log = logging.getLogger(__name__)


# ── command registration ─────────────────────────────────────────────────────


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "iconify",
        help="set each folder's cover art as its Finder icon (macOS only)",
        description=(
            "Apply PATH's cover image as its Finder icon, or with --recurse, do "
            "the same for every folder beneath it that has one. The image is "
            "padded to a square so artwork keeps its shape. macOS only."
        ),
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        type=Path,
        metavar="PATH",
        help="folder to iconify (default: current directory)",
    )
    parser.add_argument(
        "-r",
        "--recurse",
        action="store_true",
        help="also iconify subfolders, not just PATH itself",
    )
    parser.add_argument(
        "-n",
        "--dry-run",
        action="store_true",
        help="report what would happen, change nothing",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="re-apply icons to folders that already have one",
    )
    parser.set_defaults(func=run)


# ── implementation ───────────────────────────────────────────────────────────


def process(folder: Path, args: argparse.Namespace) -> str:
    """Set one folder's icon. Returns a one-word outcome."""
    cover = has_cover(folder)
    if cover is None:  # pragma: no cover - find_cover_folders only yields folders with one
        return "no-cover"

    if has_custom_icon(folder) and not args.force:
        log.info("skip   %s (icon already set)", folder.name)
        return "skipped"

    if args.dry_run:
        log.info("would  %s <- %s", folder.name, cover.name)
        return "would-set"

    # The .icns is scratch: writing it into the folder would leave litter behind
    # on failure, and could collide with the artwork we're converting.
    try:
        with tempfile.TemporaryDirectory() as scratch:
            icon = Path(scratch) / "folder.icns"
            to_icns(cover, icon)
            set_folder_icon(icon, folder)
    except (OSError, IconError) as exc:
        log.error("error  %s: %s", folder.name, exc)
        return "failed"

    log.info("set    %s <- %s", folder.name, cover.name)
    return "set"


def run(args: argparse.Namespace) -> int:
    if not is_supported():
        log.error("iconify only works on macOS")
        return 2

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        log.error("%s is not a directory", root)
        return 2

    folders = find_cover_folders(root, recurse=args.recurse)
    if not folders:
        if args.recurse:
            log.error("no folders with cover art under %s", root)
        else:
            log.error("%s has no cover art (use --recurse to scan subfolders)", root)
        return 1
    log.info("found %d folder(s) with cover art under %s\n", len(folders), root)

    counts: dict[str, int] = {}
    for folder in folders:
        outcome = process(folder, args)
        counts[outcome] = counts.get(outcome, 0) + 1

    log.info("\n%s", ", ".join(f"{count} {name}" for name, count in sorted(counts.items())))
    return 0 if not counts.get("failed") else 1
