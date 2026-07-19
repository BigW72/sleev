# sleev

Cover art for folders of music. `sleev` walks a library, works out which album each
folder holds, and downloads its front cover from the
[Cover Art Archive](https://coverartarchive.org/).

Albums are identified from the audio files' tags (`albumartist`/`artist` + `album`),
falling back to parsing the folder name when tags are missing.

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

Run `sleev <command> --help` for a command's full options.

### `sleev get`

```sh
# See what it would do, without downloading anything
uv run sleev get ~/Music --dry-run

# Fetch covers for every folder that doesn't already have one
uv run sleev get ~/Music

# Full-resolution art, replacing existing covers
uv run sleev get ~/Music --size original --overwrite
```

| Flag | Meaning |
| --- | --- |
| `-n`, `--dry-run` | Report what would happen; download nothing. |
| `-f`, `--overwrite` | Replace covers that already exist. |
| `-s`, `--size` | `250`, `500` (default), `1200`, or `original`. |
| `--name` | Filename stem to write (default `cover`; extension follows the image type). |
| `--limit` | MusicBrainz candidates to try per album (default 5). |
| `-v`, `--verbose` | Show each lookup as it happens. Accepted before or after the command. |

Folders that already contain `cover.*`, `folder.*`, `front.*`, or similar are skipped
unless `--overwrite` is passed. Your audio files are never modified.

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
