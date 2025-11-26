"""Regression coverage for the valedate test harness and helpers."""

from __future__ import annotations

import textwrap
import typing as typ

from valedate import Valedate
from valedate.assertions import (
    assert_has_diagnostic,
    assert_no_diagnostics,
    assert_only_checks,
)

if typ.TYPE_CHECKING:
    from pathlib import Path


def _ini() -> dict[str, object]:
    """Return the default .vale.ini configuration used in tests."""
    return {
        "__root__": {"MinAlertLevel": "suggestion"},
        "[*.md]": {"BasedOnStyles": "Test"},
    }


def _rule(level: str = "warning") -> str:
    """Return a YAML rule string for tests."""
    return textwrap.dedent(
        f"""
        extends: existence
        message: "Avoid 'foo'."
        level: {level}
        ignorecase: true
        tokens:
          - foo
        """
    )


def _styles(level: str = "warning") -> dict[str, str]:
    """Return mapping of style file name to rule body for the level."""
    return {"Test/NoFoo.yml": _rule(level)}


def test_lint_reports_configured_rule() -> None:
    """Lint should surface diagnostics for the configured style."""
    with Valedate(_ini(), styles=_styles()) as env:
        diags = env.lint("foo should trigger a diagnostic.")

    diag = assert_has_diagnostic(diags, check="Test.NoFoo")
    assert diag.line == 1
    assert diag.severity == "warning"


def test_lint_respects_min_alert_level() -> None:
    """Warnings should be filtered when min_alert_level is higher."""
    with Valedate(_ini(), styles=_styles(), min_alert_level="error") as env:
        diags = env.lint("foo still appears here.")

    assert_no_diagnostics(diags)


def test_lint_path_groups_alerts_by_path(tmp_path: Path) -> None:
    """lint_path should key diagnostics by the reported file path."""
    doc = tmp_path / "doc.md"
    doc.write_text("foo\nbar foo\n", encoding="utf-8")

    with Valedate(_ini(), styles=_styles()) as env:
        results = env.lint_path(doc)

    assert str(doc) in results
    alerts = results[str(doc)]
    assert_only_checks(alerts, {"Test.NoFoo"})
    assert {alert.line for alert in alerts} == {1, 2}


def test_styles_mapping_accepts_bytes() -> None:
    """In-memory styles may be provided as bytes as well as strings."""
    styles = {"Test/NoFoo.yml": _rule().encode("utf-8")}

    with Valedate(_ini(), styles=styles) as env:
        diags = env.lint("foo shows up")

    assert_has_diagnostic(diags, check="Test.NoFoo")
