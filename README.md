# sleev

Walks a music library, works out which album each folder holds, and downloads the
front cover from the [Cover Art Archive](https://coverartarchive.org/) as `cover.jpg`.

Albums are identified from the audio files' tags (`albumartist`/`artist` + `album`),
falling back to parsing the folder name when tags are missing.

## Install

```sh
uv sync
```

## Usage

```sh
# See what it would do, without downloading anything
uv run sleev ~/Music --dry-run

# Fetch covers for every folder that doesn't already have one
uv run sleev ~/Music

# Full-resolution art, replacing existing covers
uv run sleev ~/Music --size original --overwrite
```

Options:

| Flag | Meaning |
| --- | --- |
| `-n`, `--dry-run` | Report what would happen; download nothing. |
| `-f`, `--overwrite` | Replace covers that already exist. |
| `-s`, `--size` | `250`, `500` (default), `1200`, or `original`. |
| `--name` | Filename stem to write (default `cover`; extension follows the image type). |
| `--limit` | MusicBrainz candidates to try per album (default 5). |
| `-v`, `--verbose` | Show each lookup as it happens. |

Folders that already contain `cover.*`, `folder.*`, `front.*`, or similar are skipped
unless `--overwrite` is passed. Your audio files are never modified.

## Rate limiting

MusicBrainz allows one request per second, and the client holds to that — a large
library takes roughly two seconds per album. This is deliberate; don't remove it.

## Development

```sh
uv run pytest
uv run ruff check --config ruff.toml .
```
