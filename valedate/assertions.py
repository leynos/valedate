"""Assertion helpers tailored for Vale diagnostics.

These helpers keep pytest assertions concise when working with
``Valedate``. They intentionally surface the actual diagnostics in failure
messages so rule authors can quickly see what Vale emitted.
"""

from __future__ import annotations

import typing as typ

if typ.TYPE_CHECKING:
    from .harness import ValeDiagnostic


def _render_diagnostics(diags: typ.Sequence[ValeDiagnostic]) -> str:
    if not diags:
        return "(no diagnostics)"
    lines = [
        f"- {diag.check} @ line {diag.line or '?'}: {diag.message}" for diag in diags
    ]
    return "\n".join(lines)


def assert_no_diagnostics(
    diags: typ.Sequence[ValeDiagnostic], message: str | None = None
) -> None:
    """Assert that Vale emitted zero diagnostics."""
    if diags:
        details = _render_diagnostics(diags)
        raise AssertionError(message or f"Expected no diagnostics, got:\n{details}")


def assert_has_diagnostic(  # noqa: PLR0913 - explicit filters keep tests readable
    diags: typ.Sequence[ValeDiagnostic],
    *,
    check: str | None = None,
    message_contains: str | None = None,
    severity: str | None = None,
    line: int | None = None,
    match: str | None = None,
) -> ValeDiagnostic:
    """Assert that at least one diagnostic matches the filters and return it."""
    for diag in diags:
        if check is not None and diag.check != check:
            continue
        if severity is not None and diag.severity != severity:
            continue
        if line is not None and diag.line != line:
            continue
        if match is not None and diag.match != match:
            continue
        if message_contains is not None and message_contains not in diag.message:
            continue
        return diag

    expected = {
        key: value
        for key, value in {
            "check": check,
            "severity": severity,
            "line": line,
            "match": match,
            "message_contains": message_contains,
        }.items()
        if value is not None
    }
    details = _render_diagnostics(diags)
    msg = f"Expected a diagnostic matching {expected}, but got none.\n{details}"
    raise AssertionError(msg)


def assert_only_checks(
    diags: typ.Sequence[ValeDiagnostic], expected_checks: typ.Iterable[str]
) -> None:
    """Assert that diagnostics only contain the expected check identifiers."""
    expected = set(expected_checks)
    actual = {diag.check for diag in diags}
    if actual != expected:
        msg = (
            f"Expected checks {sorted(expected)}, got {sorted(actual)}.\n"
            f"Diagnostics were:\n{_render_diagnostics(diags)}"
        )
        raise AssertionError(msg)


__all__ = [
    "assert_has_diagnostic",
    "assert_no_diagnostics",
    "assert_only_checks",
]
