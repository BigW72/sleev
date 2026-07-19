# sleev

Cover art for folders of music. `sleev` works out which album a folder holds and
downloads its front cover from the
[Cover Art Archive](https://coverartarchive.org/) — one folder at a time, or a whole
library with `--recurse`.

Albums are identified from the audio files' tags (`albumartist`/`artist` + `album`),
falling back to parsing the folder name when tags are missing.

When a lookup finds nothing, it's retried with trailing qualifiers stripped from the
album title — `Animals [1997 Remaster]` becomes `Animals`, and stacked qualifiers like
`The Annual 2009 (Disc 2) (Mixed by Goodwill) [AU]` come off in one go. The archive
rarely indexes editions under their qualified name, so this recovers a lot of covers.
The second lookup only happens on a miss, and only when stripping actually changes the
title.

## Install

```sh
uv sync
```

## Usage

```
sleev <command> [options]
```

| Command | Does |
| --- | --- |
| `get` | Download missing cover art from the Cover Art Archive. |
| `iconify` | Use each folder's cover art as its Finder icon (macOS only). |

Run `sleev <command> --help` for a command's full options.

### `sleev get`

```sh
# Fetch the cover for a single album folder
uv run sleev get "~/Music/Radiohead - Kid A"

# See what it would do across a library, without downloading anything
uv run sleev get ~/Music --recurse --dry-run

# Fetch covers for every folder that doesn't already have one
uv run sleev get ~/Music --recurse

# Full-resolution art, replacing existing covers
uv run sleev get ~/Music -r --size original --overwrite
```

By default only `PATH` itself is treated as an album folder; pass `--recurse` to walk
the whole tree.

| Flag | Meaning |
| --- | --- |
| `-r`, `--recurse` | Scan subfolders too, not just `PATH` itself. |
| `-n`, `--dry-run` | Report what would happen; download nothing. |
| `-f`, `--overwrite` | Replace covers that already exist. |
| `-s`, `--size` | `250`, `500` (default), `1200`, or `original`. |
| `--min-size` | Existing covers smaller than this are replaced (default 500). |
| `--normalise` | Write every cover as `cover.png`, downloaded or existing. |
| `--name` | Filename stem to write (default `cover`; extension follows the image type). |
| `--limit` | MusicBrainz candidates to try per album (default 5). |
| `-v`, `--verbose` | Show each lookup as it happens. Accepted before or after the command. |

Your audio files are never modified.

### Existing covers

A folder already containing `cover.*`, `folder.*`, `front.*`, or similar is skipped —
but only if that image is at least 500×500. Anything smaller is treated as not good
enough, and the old file is deleted once its replacement has downloaded, so the folder
doesn't keep both. Files that aren't readable images are replaced the same way.

`--min-size` moves that threshold. It is capped at `--size`, so `--size 250` will never
throw away a 400×400 cover to fetch a smaller one.

`--normalise` (`--normalize` also works) makes every folder end up with a single
`cover.png`. Art already on disk that's worth keeping is re-encoded and the original
removed; freshly downloaded art is converted on the way in, rather than being saved
under whatever extension the archive served. Without the flag, downloads keep their
native extension and a good `folder.jpg` is left as it is.

```sh
# Tidy an existing library: everything ends up as cover.png, small art refetched
uv run sleev get ~/Music --recurse --normalise
```

### `sleev iconify`

Sets a folder's cover art as its Finder icon, so a library browses as artwork rather
than a wall of identical folders. **macOS only** — it calls `NSWorkspace.setIcon:`,
which has no cross-platform equivalent.

```sh
# One folder
uv run sleev iconify "~/Music/Radiohead - Kid A"

# A whole library, artist folders included
uv run sleev iconify ~/Music --recurse
```

| Flag | Meaning |
| --- | --- |
| `-r`, `--recurse` | Iconify subfolders too, not just `PATH` itself. |
| `-n`, `--dry-run` | Report what would happen; change nothing. |
| `-f`, `--force` | Re-apply icons to folders that already have one. |

Unlike `get`, this doesn't care about audio: any folder holding a cover image
qualifies, so artist folders and box sets get artwork too. The same filenames apply
(`cover.*`, `folder.*`, `front.*`, …), preferring `cover.png` when several exist.

Art is padded out to a square with transparency before conversion. Icons must be
square, and without the padding a tall poster gets stretched to fill one.

Folders whose icon is already set are skipped, which is what makes a re-run cheap;
`--force` overrides that. macOS records the icon in a file named `Icon\r` inside the
folder — that carriage return is real, and is how the check works.

## Rate limiting

MusicBrainz allows one request per second, and the client holds to that — a large
library takes roughly two seconds per album. This is deliberate; don't remove it.

## Adding a command

Subcommands live one-per-module under `src/sleev/commands/`. Each exposes a
`register(subparsers)` that builds its own parser and calls
`parser.set_defaults(func=run)`; `run(args)` returns a process exit code. Adding a
command means writing the module and appending it to `_COMMAND_MODULES` in
`cli.py` — the dispatcher itself never changes. This mirrors the layout used in
`kurate`.

## Development

```sh
uv run pytest
uv run ruff check .
```
