import argparse
from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest

from sleev.commands.get import keep_floor, process
from sleev.musicbrainz import Cover
from sleev.scan import Album


class FakeClient:
    """Stands in for CoverArtClient, handing back a fixed 500x500 PNG."""

    def __init__(self, cover: Cover | None = None) -> None:
        self.cover = cover if cover is not None else Cover(png(500), ".png", "mbid")
        self.calls = 0

    def find_cover(self, artist: str | None, album: str | None, **_kwargs: object) -> Cover | None:
        self.calls += 1
        return self.cover


def encode(side: int, fmt: str) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (side, side), "blue").save(buffer, fmt)
    return buffer.getvalue()


def png(side: int) -> bytes:
    return encode(side, "PNG")


def jpeg(side: int) -> bytes:
    return encode(side, "JPEG")


def write_image(path: Path, side: int) -> Path:
    Image.new("RGB", (side, side), "red").save(path)
    return path


def options(**overrides: object) -> argparse.Namespace:
    defaults = {
        "dry_run": False,
        "overwrite": False,
        "size": "500",
        "min_size": 500,
        "normalise": False,
        "name": "cover",
        "limit": 5,
    }
    return argparse.Namespace(**(defaults | overrides))


@pytest.fixture
def album(tmp_path: Path) -> Album:
    return Album(tmp_path, "Artist", "Album", "folder")


def test_small_existing_cover_is_replaced_and_removed(album: Album) -> None:
    write_image(album.path / "front.jpg", 300)
    client = FakeClient()

    assert process(album, client, options()) == "replaced"
    assert not (album.path / "front.jpg").exists()
    assert (album.path / "cover.png").exists()


def test_big_existing_cover_is_left_alone(album: Album) -> None:
    write_image(album.path / "front.jpg", 800)
    client = FakeClient()

    assert process(album, client, options()) == "skipped"
    assert client.calls == 0
    assert (album.path / "front.jpg").exists()


def test_unreadable_existing_cover_is_replaced(album: Album) -> None:
    (album.path / "cover.jpg").write_bytes(b"truncated")

    assert process(album, FakeClient(), options()) == "replaced"
    assert (album.path / "cover.png").exists()


def test_normalise_converts_a_cover_worth_keeping(album: Album) -> None:
    write_image(album.path / "folder.jpg", 800)
    client = FakeClient()

    assert process(album, client, options(normalise=True)) == "normalised"
    assert client.calls == 0
    assert not (album.path / "folder.jpg").exists()
    with Image.open(album.path / "cover.png") as image:
        assert image.format == "PNG"
        assert image.size == (800, 800)


def test_normalise_leaves_an_already_correct_cover(album: Album) -> None:
    write_image(album.path / "cover.png", 800)
    before = (album.path / "cover.png").read_bytes()

    assert process(album, FakeClient(), options(normalise=True)) == "skipped"
    assert (album.path / "cover.png").read_bytes() == before


def test_normalise_replaces_a_small_cover_with_a_png(album: Album) -> None:
    write_image(album.path / "folder.jpg", 300)

    assert process(album, FakeClient(), options(normalise=True)) == "replaced"
    assert not (album.path / "folder.jpg").exists()
    with Image.open(album.path / "cover.png") as image:
        assert image.format == "PNG"


def test_normalise_converts_a_downloaded_jpeg(album: Album) -> None:
    client = FakeClient(Cover(jpeg(500), ".jpg", "mbid"))

    assert process(album, client, options(normalise=True)) == "saved"
    assert not (album.path / "cover.jpg").exists()
    with Image.open(album.path / "cover.png") as image:
        assert image.format == "PNG"
        assert image.size == (500, 500)


def test_downloads_keep_their_own_extension_without_normalise(album: Album) -> None:
    client = FakeClient(Cover(jpeg(500), ".jpg", "mbid"))

    assert process(album, client, options()) == "saved"
    assert (album.path / "cover.jpg").exists()
    assert not (album.path / "cover.png").exists()


def test_corrupt_download_is_reported_rather_than_written(album: Album) -> None:
    client = FakeClient(Cover(b"not an image", ".jpg", "mbid"))

    assert process(album, client, options(normalise=True)) == "failed"
    assert not (album.path / "cover.png").exists()


def test_dry_run_reports_the_conversion_without_making_it(album: Album) -> None:
    write_image(album.path / "folder.jpg", 800)

    assert process(album, FakeClient(), options(normalise=True, dry_run=True)) == "would-normalise"
    assert (album.path / "folder.jpg").exists()
    assert not (album.path / "cover.png").exists()


def test_overwrite_replaces_even_a_big_cover(album: Album) -> None:
    write_image(album.path / "folder.jpg", 1200)

    assert process(album, FakeClient(), options(overwrite=True)) == "replaced"
    assert not (album.path / "folder.jpg").exists()


@pytest.mark.parametrize(
    ("size", "min_size", "expected"),
    [
        ("500", 500, 500),
        ("250", 500, 250),  # never discard art bigger than what we'd fetch
        ("1200", 500, 500),
        ("original", 500, 500),
    ],
)
def test_keep_floor_never_exceeds_the_download_size(size: str, min_size: int, expected: int) -> None:
    assert keep_floor(options(size=size, min_size=min_size)) == expected
