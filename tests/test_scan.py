from pathlib import Path

import pytest

from sleev.scan import find_album_folders, has_cover, parse_folder_name, strip_qualifiers


@pytest.mark.parametrize(
    ("album", "expected"),
    [
        ("Kid A", "Kid A"),
        ("Animals [1997 Remaster]", "Animals"),
        ("A2G (EP)", "A2G"),
        ("Beck - Guero [Deluxe Version]", "Beck - Guero"),
        # Tags stack qualifiers, so stripping has to repeat.
        ("The Annual 2009 (Disc 2) (Mixed by Goodwill) [AU]", "The Annual 2009"),
        ("Amon Tobin (Boxset) [Downloads]", "Amon Tobin"),
        # A leading bracket is part of the title, not a qualifier.
        ("(Who's Afraid Of?) The Art of Noise", "(Who's Afraid Of?) The Art of Noise"),
        # Nothing but a qualifier: better to search it than an empty string.
        ("(EP)", "(EP)"),
        ("", ""),
    ],
)
def test_strip_qualifiers(album: str, expected: str) -> None:
    assert strip_qualifiers(album) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Radiohead - Kid A", ("Radiohead", "Kid A")),
        ("Radiohead - Kid A (2000)", ("Radiohead", "Kid A")),
        ("Boards of Canada -- Geogaddi [FLAC]", ("Boards of Canada", "Geogaddi")),
        ("Kid A", (None, "Kid A")),
        ("", (None, None)),
    ],
)
def test_parse_folder_name(name: str, expected: tuple[str | None, str | None]) -> None:
    assert parse_folder_name(name) == expected


def test_find_album_folders_recursing_only_returns_dirs_with_audio(tmp_path: Path) -> None:
    (tmp_path / "Artist - Album").mkdir()
    (tmp_path / "Artist - Album" / "01.flac").touch()
    (tmp_path / "Artwork").mkdir()
    (tmp_path / "Artwork" / "scan.png").touch()

    found = find_album_folders(tmp_path, recurse=True)

    assert [a.path.name for a in found] == ["Artist - Album"]
    assert found[0].artist == "Artist"
    assert found[0].album == "Album"
    assert found[0].source == "folder"


def test_find_album_folders_defaults_to_the_root_only(tmp_path: Path) -> None:
    root = tmp_path / "Artist - Album"
    root.mkdir()
    (root / "01.flac").touch()
    (root / "CD2").mkdir()
    (root / "CD2" / "01.flac").touch()

    assert [a.path for a in find_album_folders(root)] == [root]
    assert len(find_album_folders(root, recurse=True)) == 2


def test_find_album_folders_ignores_a_root_without_audio(tmp_path: Path) -> None:
    (tmp_path / "Artist - Album").mkdir()
    (tmp_path / "Artist - Album" / "01.flac").touch()

    assert find_album_folders(tmp_path) == []


def test_has_cover_recognises_common_filenames(tmp_path: Path) -> None:
    assert has_cover(tmp_path) is None
    (tmp_path / "folder.jpg").touch()
    assert has_cover(tmp_path).name == "folder.jpg"


def test_has_cover_ignores_unrelated_images(tmp_path: Path) -> None:
    (tmp_path / "back.jpg").touch()
    assert has_cover(tmp_path) is None
