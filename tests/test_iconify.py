import argparse
from pathlib import Path

from PIL import Image
import pytest

from sleev.commands.iconify import process
from sleev.icons import ICON_RESOURCE, has_custom_icon
from sleev.images import to_icns
from sleev.scan import find_cover_folders, has_cover


def write_image(path: Path, size: tuple[int, int] = (600, 600)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "red").save(path)
    return path


def options(**overrides: object) -> argparse.Namespace:
    return argparse.Namespace(**({"dry_run": False, "force": False} | overrides))


@pytest.fixture
def applied(monkeypatch: pytest.MonkeyPatch) -> list[tuple[Path, Path]]:
    """Record set_folder_icon calls instead of touching the real Finder."""
    calls: list[tuple[Path, Path]] = []
    monkeypatch.setattr(
        "sleev.commands.iconify.set_folder_icon",
        lambda icon, folder: calls.append((icon, folder)),
    )
    return calls


# ── conversion ───────────────────────────────────────────────────────────────


def test_to_icns_pads_a_tall_cover_instead_of_stretching_it(tmp_path: Path) -> None:
    source = write_image(tmp_path / "poster.png", (600, 900))

    to_icns(source, tmp_path / "out.icns")

    with Image.open(tmp_path / "out.icns") as icon:
        assert icon.width == icon.height
    # The padding is transparent, so the corners either side of a tall image
    # must not have picked up the artwork's colour.
    with Image.open(tmp_path / "out.icns") as icon:
        assert icon.convert("RGBA").getpixel((5, icon.height // 2))[3] == 0


def test_to_icns_handles_a_square_cover(tmp_path: Path) -> None:
    to_icns(write_image(tmp_path / "cover.png"), tmp_path / "out.icns")

    with Image.open(tmp_path / "out.icns") as icon:
        assert icon.width == icon.height


# ── discovery ────────────────────────────────────────────────────────────────


def test_find_cover_folders_ignores_folders_without_art(tmp_path: Path) -> None:
    write_image(tmp_path / "Artist" / "Album" / "cover.png")
    (tmp_path / "Artist" / "Empty").mkdir()

    found = find_cover_folders(tmp_path, recurse=True)

    assert [f.name for f in found] == ["Album"]


def test_find_cover_folders_does_not_require_audio(tmp_path: Path) -> None:
    write_image(tmp_path / "Films" / "Alien" / "cover.jpg")

    assert [f.name for f in find_cover_folders(tmp_path, recurse=True)] == ["Alien"]


def test_find_cover_folders_defaults_to_the_root_only(tmp_path: Path) -> None:
    write_image(tmp_path / "cover.png")
    write_image(tmp_path / "Child" / "cover.png")

    assert find_cover_folders(tmp_path) == [tmp_path]
    assert len(find_cover_folders(tmp_path, recurse=True)) == 2


def test_has_cover_prefers_cover_png_over_other_names(tmp_path: Path) -> None:
    write_image(tmp_path / "folder.jpg")
    write_image(tmp_path / "cover.png")

    assert has_cover(tmp_path).name == "cover.png"


def test_has_cover_prefers_png_over_jpg_for_the_same_stem(tmp_path: Path) -> None:
    write_image(tmp_path / "cover.jpg")
    write_image(tmp_path / "cover.png")

    assert has_cover(tmp_path).name == "cover.png"


# ── the command ──────────────────────────────────────────────────────────────


def test_process_sets_an_icon(tmp_path: Path, applied: list[tuple[Path, Path]]) -> None:
    write_image(tmp_path / "cover.png")

    assert process(tmp_path, options()) == "set"
    assert len(applied) == 1
    icon, folder = applied[0]
    assert folder == tmp_path
    assert icon.suffix == ".icns"


def test_process_skips_a_folder_that_already_has_an_icon(
    tmp_path: Path, applied: list[tuple[Path, Path]]
) -> None:
    write_image(tmp_path / "cover.png")
    (tmp_path / ICON_RESOURCE).touch()

    assert process(tmp_path, options()) == "skipped"
    assert applied == []


def test_force_reapplies_an_existing_icon(
    tmp_path: Path, applied: list[tuple[Path, Path]]
) -> None:
    write_image(tmp_path / "cover.png")
    (tmp_path / ICON_RESOURCE).touch()

    assert process(tmp_path, options(force=True)) == "set"
    assert len(applied) == 1


def test_dry_run_changes_nothing(tmp_path: Path, applied: list[tuple[Path, Path]]) -> None:
    write_image(tmp_path / "cover.png")

    assert process(tmp_path, options(dry_run=True)) == "would-set"
    assert applied == []


def test_process_reports_a_corrupt_cover_rather_than_raising(
    tmp_path: Path, applied: list[tuple[Path, Path]]
) -> None:
    (tmp_path / "cover.png").write_bytes(b"not an image")

    assert process(tmp_path, options()) == "failed"
    assert applied == []


def test_the_scratch_icns_does_not_survive_in_the_folder(
    tmp_path: Path, applied: list[tuple[Path, Path]]
) -> None:
    write_image(tmp_path / "cover.png")

    process(tmp_path, options())

    assert [p.name for p in tmp_path.iterdir()] == ["cover.png"]


def test_has_custom_icon_reads_the_carriage_return_file(tmp_path: Path) -> None:
    assert not has_custom_icon(tmp_path)
    (tmp_path / ICON_RESOURCE).touch()
    assert has_custom_icon(tmp_path)
