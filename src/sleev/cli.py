"""sleev command-line interface — dispatches to subcommands.

Each subcommand lives in its own module under `sleev.commands` and exposes
a `register(subparsers)` function. Adding a new subcommand is therefore
"add a module + import it below" — the dispatcher itself never changes.
"""

import argparse
import logging
import sys

from sleev import __version__
from sleev.commands import get

_COMMAND_MODULES = (get,)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sleev",
        description="Manage cover art for folders of music.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="show per-request detail")

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    for module in _COMMAND_MODULES:
        module.register(subparsers)

    # Accept -v after the subcommand too ("sleev get PATH -v"), which is what
    # people type. SUPPRESS keeps the subparser from resetting a -v given
    # before the subcommand back to False.
    for subparser in subparsers.choices.values():
        subparser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
            default=argparse.SUPPRESS,
            help="show per-request detail",
        )

    return parser


def configure_logging(*, verbose: bool) -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    logging.getLogger("sleev").setLevel(logging.DEBUG if verbose else logging.INFO)
    # httpx/httpcore log every socket operation at DEBUG, which buries our own output.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    configure_logging(verbose=args.verbose)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
