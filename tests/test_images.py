from pathlib import Path

from PIL import Image
import pytest

from sleev.images import dimensions, to_png


def write_image(path: Path, size: tuple[int, int] = (600, 600), mode: str = "RGB") -> Path:
    Image.new(mode, size, "red").save(path)
    return path


def test_dimensions_reads_the_pixel_size(tmp_path: Path) -> None:
    assert dimensions(write_image(tmp_path / "cover.jpg", (300, 450))) == (300, 450)


@pytest.mark.parametrize("content", [b"", b"not an image at all"])
def test_dimensions_returns_none_for_unreadable_files(tmp_path: Path, content: bytes) -> None:
    path = tmp_path / "cover.jpg"
    path.write_bytes(content)
    assert dimensions(path) is None


def test_to_png_converts_and_removes_the_original(tmp_path: Path) -> None:
    source = write_image(tmp_path / "folder.jpg")
    destination = tmp_path / "cover.png"

    to_png(source, destination)

    assert not source.exists()
    with Image.open(destination) as image:
        assert image.format == "PNG"
        assert image.size == (600, 600)


def test_to_png_keeps_alpha(tmp_path: Path) -> None:
    source = write_image(tmp_path / "folder.png", mode="RGBA")

    to_png(source, tmp_path / "cover.png")

    with Image.open(tmp_path / "cover.png") as image:
        assert image.mode == "RGBA"


def test_to_png_leaves_the_file_alone_when_source_is_the_destination(tmp_path: Path) -> None:
    path = write_image(tmp_path / "cover.png")

    to_png(path, path)

    assert path.exists()
