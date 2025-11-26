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
    """Render diagnostics as a readable string."""
    if not diags:
        return "(no diagnostics)"
    lines = [
        f"- {diag.check} @ line {diag.line or '?'}: {diag.message}" for diag in diags
    ]
    return "\n".join(lines)


def assert_no_diagnostics(
    diags: typ.Sequence[ValeDiagnostic], message: str | None = None
) -> None:
    """Assert that Vale emitted zero diagnostics.

    Parameters
    ----------
    diags : Sequence[ValeDiagnostic]
        Diagnostics returned by Vale for an input.
    message : str | None, optional
        Custom assertion failure message. When omitted, a rendered listing of
        diagnostics is appended to the default message.

    Returns
    -------
    None

    Raises
    ------
    AssertionError
        If any diagnostics are present; the error message includes the
        rendered diagnostics.

    """
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
    """Assert that at least one diagnostic matches the filters and return it.

    Parameters
    ----------
    diags : Sequence[ValeDiagnostic]
        Diagnostics returned by Vale.
    check : str | None, optional
        Fully-qualified check name to match (e.g., ``concordat.NoFoo``).
    message_contains : str | None, optional
        Substring that must appear within the diagnostic message.
    severity : str | None, optional
        Exact severity value to match (e.g., ``warning`` or ``error``).
    line : int | None, optional
        Expected one-based line number for the diagnostic.
    match : str | None, optional
        Matched text snippet to match exactly against ``diag.match``.

    Returns
    -------
    ValeDiagnostic
        The first diagnostic satisfying all provided filters.

    Raises
    ------
    AssertionError
        If no diagnostic satisfies the filters; the error message includes all
        diagnostics rendered for debugging.

    Examples
    --------
    >>> diag = assert_has_diagnostic(diags, check="Test.NoFoo", line=1)
    >>> diag.severity
    'warning'

    """
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
    """Assert that diagnostics only contain the expected check identifiers.

    This assertion compares the set of check identifiers present in the
    diagnostics with the expected set and raises if they differ.

    Parameters
    ----------
    diags : Sequence[ValeDiagnostic]
        Diagnostics returned by Vale.
    expected_checks : Iterable[str]
        Iterable of expected fully-qualified check identifiers.

    Returns
    -------
    None

    Raises
    ------
    AssertionError
        If the actual set of check identifiers does not exactly match the
        expected set. The error message includes a rendered list of
        diagnostics.

    """
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
