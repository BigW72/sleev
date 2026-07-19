from pathlib import Path

import pytest

from sleev.scan import (
    artist_from_parent,
    describe_folder,
    find_album_folders,
    has_cover,
    parse_folder_name,
    strip_qualifiers,
)


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
        # "Artist - YYYY - Album", the dominant layout in folder-named libraries.
        ("AC DC - 1979 - Highway To Hell", ("AC DC", "Highway To Hell")),
        ("AC DC - 1979 - Highway To Hell [2003 Remaster]", ("AC DC", "Highway To Hell")),
        # The album may itself contain a dash.
        (
            "Angelo Badalamenti - 2007 - Twin Peaks - Season Two (OST)",
            ("Angelo Badalamenti", "Twin Peaks - Season Two"),
        ),
        # Albums that are years must survive the year pattern.
        ("Dr. Dre - 1999 - 2001", ("Dr. Dre", "2001")),
        ("Taylor Swift - 2014 - 1989", ("Taylor Swift", "1989")),
        ("Summer Trance Top 50 - 2013 - 2013", ("Summer Trance Top 50", "2013")),
        ("The Beatles - 1993 - 1962-1966", ("The Beatles", "1962-1966")),
        # "Album (OST) - YYYY" carries no artist; the generic pattern would
        # otherwise read the film as the artist and the year as the album.
        ("A Clockwork Orange (OST) - 1972", (None, "A Clockwork Orange")),
        ("(500) Days Of Summer (OST) - 2009", (None, "(500) Days Of Summer")),
        # A title that is nothing but brackets is not noise.
        ("Sigur Rós - 2002 - ( )", ("Sigur Rós", "( )")),
        # A leading bracket belongs to the title.
        ("Art of Noise - 1984 - (Who's Afraid Of?) The Art of Noise",
         ("Art of Noise", "(Who's Afraid Of?) The Art of Noise")),
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
    (root / "Bonus Tracks").mkdir()
    (root / "Bonus Tracks" / "01.flac").touch()

    assert [a.path for a in find_album_folders(root)] == [root]
    assert len(find_album_folders(root, recurse=True)) == 2


def test_find_album_folders_ignores_a_root_without_audio(tmp_path: Path) -> None:
    (tmp_path / "Artist - Album").mkdir()
    (tmp_path / "Artist - Album" / "01.flac").touch()

    assert find_album_folders(tmp_path) == []


@pytest.mark.parametrize(
    ("parent", "expected"),
    [
        # The usual Artist/Album layout.
        ("Radiohead", "Radiohead"),
        ("DJ-Kicks", "DJ-Kicks"),
        # A box set's discs sit inside another album folder, so parse it.
        ("Depeche Mode - 2004 - DMBX The Singles", "Depeche Mode"),
        # Collection markers are not artists.
        ("#va", None),
        ("#ost", None),
        # An album folder naming no artist has none to lend.
        ("MTVExtreme - 2001", None),
        ("A Clockwork Orange (OST) - 1972", None),
    ],
)
def test_artist_from_parent(tmp_path: Path, parent: str, expected: str | None) -> None:
    folder = tmp_path / parent / "Disc 1"
    folder.mkdir(parents=True)

    assert artist_from_parent(folder, tmp_path) == expected


def test_artist_from_parent_ignores_the_scan_root(tmp_path: Path) -> None:
    # Pointing sleev at one album shouldn't drag in the folder above it.
    album = tmp_path / "Radiohead" / "Kid A"
    album.mkdir(parents=True)

    assert artist_from_parent(album, album) is None
    assert artist_from_parent(album, None) is None


def test_describe_folder_falls_back_to_the_parent_for_the_artist(tmp_path: Path) -> None:
    album = tmp_path / "Radiohead" / "Kid A"
    album.mkdir(parents=True)
    (album / "01.flac").touch()

    described = describe_folder(album, tmp_path)

    assert (described.artist, described.album) == ("Radiohead", "Kid A")


def test_describe_folder_keeps_an_artist_from_the_folder_name(tmp_path: Path) -> None:
    album = tmp_path / "Compilations" / "Radiohead - 2000 - Kid A"
    album.mkdir(parents=True)
    (album / "01.flac").touch()

    described = describe_folder(album, tmp_path)

    assert described.artist == "Radiohead"


def make_album(folder: Path, *discs: str) -> Path:
    """An album folder holding only disc subfolders, as a box set does."""
    folder.mkdir(parents=True)
    for disc in discs:
        (folder / disc).mkdir()
        (folder / disc / "01.flac").touch()
    return folder


def test_box_set_is_one_album_covering_every_disc(tmp_path: Path) -> None:
    box = make_album(
        tmp_path / "Artist" / "Depeche Mode - 2004 - DMBX The Singles",
        "DMBX The Singles (Disc 1)",
        "DMBX The Singles (Disc 2)",
    )

    found = find_album_folders(tmp_path, recurse=True)

    # One lookup, not one per disc, and the parent gets art despite holding
    # no audio of its own.
    assert [a.path for a in found] == [box]
    assert [d.name for d in found[0].discs] == [
        "DMBX The Singles (Disc 1)",
        "DMBX The Singles (Disc 2)",
    ]
    assert found[0].folders == (box, *found[0].discs)
    assert found[0].album == "DMBX The Singles"


def test_the_canonical_layout(tmp_path: Path) -> None:
    """Artist/Album/Album (Disc N) — the layout this library is kept in."""
    (tmp_path / "Radiohead" / "OK Computer").mkdir(parents=True)
    (tmp_path / "Radiohead" / "OK Computer" / "01.flac").touch()
    make_album(tmp_path / "Radiohead" / "Kid A", "Kid A (Disc 1)", "Kid A (Disc 2)")

    found = {a.path.name: a for a in find_album_folders(tmp_path, recurse=True)}

    # The artist folder is not an album, and the single-disc sibling is
    # unaffected by the box set beside it.
    assert set(found) == {"Kid A", "OK Computer"}
    assert found["Kid A"].artist == "Radiohead"
    assert found["Kid A"].album == "Kid A"
    assert [d.name for d in found["Kid A"].discs] == ["Kid A (Disc 1)", "Kid A (Disc 2)"]
    assert found["OK Computer"].discs == ()


def test_bare_disc_folders_are_grouped(tmp_path: Path) -> None:
    box = make_album(tmp_path / "Radiohead - 2000 - Kid A", "Disc 1", "CD2")

    found = find_album_folders(tmp_path, recurse=True)

    assert [a.path for a in found] == [box]
    assert len(found[0].discs) == 2
    assert found[0].album == "Kid A"


def test_discs_beside_each_other_under_an_artist_are_not_grouped(tmp_path: Path) -> None:
    # Layout A: the discs are siblings under the artist, so the artist folder
    # must not be mistaken for an album.
    artist = tmp_path / "Basement Jaxx"
    for disc in ("Basement Jaxx - 2005 - The Singles (Disc 1)",
                 "Basement Jaxx - 2005 - The Singles (Disc 2)"):
        (artist / disc).mkdir(parents=True)
        (artist / disc / "01.flac").touch()

    found = find_album_folders(tmp_path, recurse=True)

    assert [a.path.name for a in found] == [
        "Basement Jaxx - 2005 - The Singles (Disc 1)",
        "Basement Jaxx - 2005 - The Singles (Disc 2)",
    ]
    assert all(a.discs == () for a in found)
    assert all(a.album == "The Singles" for a in found)


def test_a_box_set_is_grouped_without_recursing(tmp_path: Path) -> None:
    box = make_album(tmp_path / "Artist - 1999 - Boxed", "Boxed (Disc 1)", "Boxed (Disc 2)")

    found = find_album_folders(box)

    assert [a.path for a in found] == [box]
    assert len(found[0].discs) == 2


def test_has_cover_recognises_common_filenames(tmp_path: Path) -> None:
    assert has_cover(tmp_path) is None
    (tmp_path / "folder.jpg").touch()
    assert has_cover(tmp_path).name == "folder.jpg"


def test_has_cover_ignores_unrelated_images(tmp_path: Path) -> None:
    (tmp_path / "back.jpg").touch()
    assert has_cover(tmp_path) is None
