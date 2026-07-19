import argparse
import logging

import pytest

from sleev.cli import build_parser, main
from sleev.commands import get


def test_get_is_registered_and_dispatches_to_its_run() -> None:
    args = build_parser().parse_args(["get", "/music"])
    assert args.func is get.run
    assert str(args.root) == "/music"


def test_recurse_is_off_by_default_and_has_a_short_form() -> None:
    assert build_parser().parse_args(["get", "/music"]).recurse is False
    assert build_parser().parse_args(["get", "/music", "-r"]).recurse is True
    assert build_parser().parse_args(["get", "/music", "--recurse"]).recurse is True


def test_verbose_accepted_before_subcommand() -> None:
    assert build_parser().parse_args(["-v", "get"]).verbose is True


def test_verbose_accepted_after_subcommand() -> None:
    assert build_parser().parse_args(["get", "-v"]).verbose is True


def test_verbose_before_subcommand_is_not_reset_by_the_subparser() -> None:
    # The subparser's own -v defaults to SUPPRESS precisely so this stays True.
    assert build_parser().parse_args(["-v", "get", "/music"]).verbose is True


def test_verbose_defaults_off() -> None:
    assert build_parser().parse_args(["get"]).verbose is False


def test_no_subcommand_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args([])
    assert exc.value.code == 2


def test_main_returns_the_commands_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get, "run", lambda args: 3)
    assert main(["get", "/music"]) == 3


def test_main_handles_keyboard_interrupt(monkeypatch: pytest.MonkeyPatch) -> None:
    def interrupt(args: argparse.Namespace) -> int:
        raise KeyboardInterrupt

    monkeypatch.setattr(get, "run", interrupt)
    assert main(["get", "/music"]) == 130


def test_verbose_sets_the_package_log_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get, "run", lambda args: 0)
    main(["get", "/music", "-v"])
    assert logging.getLogger("sleev").level == logging.DEBUG
    main(["get", "/music"])
    assert logging.getLogger("sleev").level == logging.INFO
