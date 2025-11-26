"""Vale testing harness for reusable rule validation.

This module mirrors the test helper originally shipped with
``concordat-vale`` and is now packaged as ``valedate`` so any Vale ruleset
author can spin up an isolated sandbox for pytest-based workflows. It
materialises a temporary ``styles/`` tree, writes a bespoke ``.vale.ini``,
shells out to the Vale CLI, and decodes JSON diagnostics into typed
structures. The harness **depends on a ``vale`` binary being available on the
``PATH``**; no mock or stub is provided because the goal is to exercise Vale
exactly as it will run in production.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import os
import re
import shutil
import subprocess
import tempfile
import typing as typ
from pathlib import Path

import msgspec
import msgspec.json as msjson

if typ.TYPE_CHECKING:
    from types import TracebackType


IniLike = str | os.PathLike[str] | typ.Mapping[str, typ.Any]
StylesLike = Path | typ.Mapping[str, str | bytes]
_VALE_RUNTIME_FAILURE_EXIT = 2


class ValedateError(RuntimeError):
    """Base exception for harness failures."""


class InvalidIniSectionError(ValedateError):
    """Raised when a pseudo-section does not map to key/value content."""

    def __init__(self, section: str) -> None:
        super().__init__(f"Section {section!r} must map to a dict of key/value pairs.")


class UnsupportedIniInputError(ValedateError):
    """Raised when the ini argument is of an unsupported type."""

    def __init__(self) -> None:
        super().__init__("ini must be a path, raw ini string, or mapping")


class StylesTreeMissingError(ValedateError):
    """Raised when the requested styles directory is absent."""

    def __init__(self, styles: Path) -> None:
        super().__init__(f"Styles tree {styles} doesn't exist")


class StylesTreeTypeError(ValedateError):
    """Raised when the styles argument resolves to a non-directory."""

    def __init__(self, styles: Path) -> None:
        super().__init__(f"Styles tree {styles} must be a directory")


class ValeExecutionError(ValedateError):
    """Raised when Vale returns a runtime failure."""

    def __init__(self, exit_code: int, stderr: str) -> None:
        """Initialise with Vale's failure metadata.

        Parameters
        ----------
        exit_code : int
            Non-zero exit status returned by the Vale process.
        stderr : str
            Captured standard error output from the Vale invocation.

        """
        super().__init__(f"Vale failed with exit code {exit_code}")
        self.exit_code = exit_code
        self.stderr = stderr


class ValeBinaryNotFoundError(FileNotFoundError, ValedateError):
    """Raised when the Vale executable cannot be located."""

    def __init__(self, binary: str) -> None:
        """Initialise with a helpful message naming the missing binary.

        Parameters
        ----------
        binary : str
            Executable name or path that failed lookup.

        """
        message = (
            f"Couldn't find '{binary}' on PATH. Install Vale or set vale_bin "
            "explicitly."
        )
        super().__init__(message)


class ValeAction(msgspec.Struct, kw_only=True):
    """Structured representation of Vale's optional Action payload.

    Attributes
    ----------
    name : str | None, optional
        Vale's ``Action.Name`` field. Defaults to ``None`` if the rule did not
        attach an action.
    params : list[str] | None, optional
        Vale's ``Action.Params`` field. Defaults to ``None`` when the rule has
        no actionable remediation parameters.

    """

    name: str | None = msgspec.field(default=None, name="Name")
    params: list[str] | None = msgspec.field(default=None, name="Params")


class ValeDiagnostic(msgspec.Struct, kw_only=True):
    """Structured representation of Vale's ``core.Alert`` payload.

    Attributes
    ----------
    check : str
        Fully-qualified rule name, for example ``concordat.RuleName``.
    message : str
        Human-readable explanation attached to the alert.
    severity : str
        Vale's severity level such as ``warning`` or ``error``.
    line : int | None, optional
        One-based line number where the alert originated, or ``None`` when
        Vale omits location metadata.
    span : tuple[int, int], optional
        Start/end offsets for the match within the line. Defaults to ``(0, 0)``
        when Vale omits span data.
    link : str | None, optional
        Optional documentation link describing the rule.
    description : str | None, optional
        Optional long-form explanation of the rule.
    match : str | None, optional
        Matched text snippet if provided by Vale.
    action : ValeAction | None, optional
        Optional structured remediation metadata exposed by the rule.

    """

    check: str = msgspec.field(name="Check")
    message: str = msgspec.field(name="Message")
    severity: str = msgspec.field(name="Severity")
    line: int | None = msgspec.field(default=None, name="Line")
    span: tuple[int, int] = msgspec.field(default=(0, 0), name="Span")
    link: str | None = msgspec.field(default=None, name="Link")
    description: str | None = msgspec.field(default=None, name="Description")
    match: str | None = msgspec.field(default=None, name="Match")
    action: ValeAction | None = msgspec.field(default=None, name="Action")


def _which_vale(vale_bin: str) -> str:
    path = shutil.which(vale_bin)
    if path is None:
        raise ValeBinaryNotFoundError(vale_bin)
    return path


def _vale_supports_stdin_flag(vale_bin: str) -> bool:
    """Return True if the Vale binary understands the --stdin flag."""
    probe = subprocess.run(  # noqa: S603
        [vale_bin, "--help"],
        capture_output=True,
        check=False,
        text=True,
    )
    help_text = (probe.stdout or "") + (probe.stderr or "")
    return "--stdin" in help_text


def _read_ini_from_text_or_path(text: str) -> str:
    """Return ini contents, preferring file reads when the string is a path."""
    candidate = Path(text)
    return candidate.read_text(encoding="utf-8") if candidate.exists() else text


def _read_ini_from_pathlike(path_like: os.PathLike[str]) -> str:
    """Read ini contents from a path-like object or raise when missing."""
    candidate = Path(os.fspath(path_like))
    if candidate.exists():
        return candidate.read_text(encoding="utf-8")
    msg = f"INI path {candidate} does not exist"
    raise FileNotFoundError(msg)


def _emit_section(lines: list[str], body: typ.Mapping[str, typ.Any]) -> None:
    """Render a mapping into key/value lines for a .vale.ini section."""
    for key, value in body.items():
        match value:
            case list() | tuple():
                rendered = ", ".join(map(str, value))
            case _:
                rendered = str(value)
        lines.append(f"{key} = {rendered}")


def _render_mapping_ini(mapping: cabc.Mapping[str, typ.Any]) -> str:
    """Render mapping-based ini input into canonical text form."""
    lines: list[str] = []

    root = mapping.get("__root__", mapping.get("top", {}))
    match root:
        case cabc.Mapping() as mapping_root:
            _emit_section(lines, mapping_root)

    for section, body in mapping.items():
        if section in {"__root__", "top"}:
            continue
        header = section if str(section).startswith("[") else f"[{section}]"
        lines.append("")
        match body:
            case cabc.Mapping() as mapping_body:
                lines.append(header)
                _emit_section(lines, mapping_body)
            case _:
                raise InvalidIniSectionError(str(section))

    return "\n".join(lines).strip() + "\n"


def _as_ini_text(ini: IniLike) -> str:
    """Normalise .vale.ini input into a text blob."""
    match ini:
        case str() as text:
            return _read_ini_from_text_or_path(text)
        case os.PathLike() as path_like:
            return _read_ini_from_pathlike(path_like)
        case cabc.Mapping() as mapping:
            return _render_mapping_ini(mapping)
        case _:
            raise UnsupportedIniInputError


def _force_styles_path(ini_text: str, styles_dirname: str = "styles") -> str:
    pattern = r"(?m)^\s*StylesPath\s*=.*$"
    if re.search(pattern, ini_text):
        return re.sub(pattern, f"StylesPath = {styles_dirname}", ini_text)
    return f"StylesPath = {styles_dirname}\n{ini_text}"


def _materialise_tree(root: Path, mapping: typ.Mapping[str, str | bytes]) -> None:
    for rel_path, contents in mapping.items():
        destination = root / rel_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        match contents:
            case bytes():
                destination.write_bytes(contents)
            case str():
                destination.write_text(contents, encoding="utf-8")
            case _:
                msg = (
                    "style file contents must be str or bytes, got "
                    f"{type(contents).__name__}"
                )
                raise TypeError(msg)


def _copy_styles_into(dst: Path, styles: Path) -> None:
    if not styles.exists():
        raise StylesTreeMissingError(styles)
    if not styles.is_dir():
        raise StylesTreeTypeError(styles)
    for item in styles.iterdir():
        target = dst / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _decode_vale_json(stdout: str) -> dict[str, list[ValeDiagnostic]]:
    value = msjson.decode(stdout)

    def _to_alerts(seq: object) -> list[ValeDiagnostic]:
        return msgspec.convert(seq, type=list[ValeDiagnostic])

    match value:
        case dict():
            return {str(path): _to_alerts(alerts) for path, alerts in value.items()}
        case [dict() as first, *_] if {"Path", "Alerts"} <= set(first):
            output: dict[str, list[ValeDiagnostic]] = {}
            for file_obj in value:
                path = str(file_obj["Path"])
                output[path] = _to_alerts(file_obj["Alerts"])
            return output
        case list():
            return {"<stdin>": _to_alerts(value)}
        case _:
            return {}


class Valedate:
    """Manage a temporary Vale environment tailored for tests.

    Parameters
    ----------
    ini : IniLike
        Either a raw ``.vale.ini`` string, a filesystem path, or dictionary
        representation describing the desired configuration.
    styles : StylesLike | None, optional
        Existing ``styles/`` directory or an in-memory tree to copy into the
        sandbox. Defaults to ``None`` for tests that only rely on built-in
        styles.
    vale_bin : str, default "vale"
        Vale executable name or path to invoke. This harness expects the
        binary to be available and will fail fast if it is missing.
    stdin_ext : str, default ".md"
        Extension to associate with stdin content so Vale selects the right
        lexer and scopes.
    auto_sync : bool, default False
        When ``True`` and the configuration declares ``Packages``, the harness
        runs ``vale sync`` once to resolve dependencies.
    min_alert_level : str | None, optional
        Default ``--minAlertLevel`` flag applied to all lint operations.

    Raises
    ------
    ValeBinaryNotFoundError
        Raised when ``vale_bin`` cannot be located on ``PATH``.

    """

    def __init__(  # noqa: PLR0913
        self,
        ini: IniLike,
        *,
        styles: StylesLike | None = None,
        vale_bin: str = "vale",
        stdin_ext: str = ".md",
        auto_sync: bool = False,
        min_alert_level: str | None = None,
    ) -> None:
        """Build a temporary Vale sandbox with the supplied configuration.

        Parameters
        ----------
        ini : IniLike
            Raw `.vale.ini` string, a path to ini content, or a mapping that
            will be rendered into ini text.
        styles : StylesLike | None, optional
            Existing `styles/` directory or in-memory mapping of style files to
            contents. When ``None``, only built-in styles are available.
        vale_bin : str, default "vale"
            Vale executable name or explicit path to invoke.
        stdin_ext : str, default ".md"
            Extension associated with stdin content so Vale chooses the
            correct lexer.
        auto_sync : bool, default False
            When true and the ini declares packages, run ``vale sync`` once
            after setup.
        min_alert_level : str | None, optional
            Default ``--minAlertLevel`` applied to all lint operations unless
            overridden per call.

        """
        with contextlib.ExitStack() as stack:
            tmp_obj = tempfile.TemporaryDirectory(prefix="valedate-")
            stack.enter_context(tmp_obj)
            tmp_path = Path(tmp_obj.name)

            self.root = tmp_path
            self.vale_bin = _which_vale(vale_bin)
            self._stdin_flag_supported = _vale_supports_stdin_flag(self.vale_bin)
            self.stdin_ext = stdin_ext
            self.default_min_level = min_alert_level

            styles_dir = self.root / "styles"
            styles_dir.mkdir(parents=True, exist_ok=True)
            self._populate_styles(styles_dir, styles)

            ini_text = _force_styles_path(_as_ini_text(ini), styles_dirname="styles")
            self.ini_path = self.root / ".vale.ini"
            self.ini_path.write_text(ini_text, encoding="utf-8")

            if auto_sync and re.search(r"(?m)^\s*Packages\s*=", ini_text):
                self._run(["sync"])

            # TemporaryDirectory is entered via ExitStack so it is cleaned if
            # any setup step fails. Once initialisation succeeds, the object is
            # stored on self._tmp and pop_all() transfers ownership so cleanup
            # occurs when the harness calls self._tmp.cleanup().
            self._tmp = tmp_obj
            stack.pop_all()

    def _populate_styles(self, styles_dir: Path, styles: StylesLike | None) -> None:
        match styles:
            case cabc.Mapping():
                mapping_styles = typ.cast(
                    "cabc.Mapping[str, str | bytes]",
                    styles,
                )
                _materialise_tree(styles_dir, mapping_styles)
            case Path():
                _copy_styles_into(styles_dir, styles)
            case None:
                pass
            case _:
                msg = (
                    "styles must be Path, Mapping, or None, got "
                    f"{type(styles).__name__}"
                )
                raise TypeError(msg)

    def lint(
        self,
        text: str,
        *,
        ext: str | None = None,
        min_alert_level: str | None = None,
    ) -> typ.Sequence[ValeDiagnostic]:
        """Lint a string inside the temporary environment.

        Parameters
        ----------
        text : str
            Markdown (or other supported format) source to lint.
        ext : str, optional
            Override for the stdin extension. Falls back to ``stdin_ext`` when
            ``None``.
        min_alert_level : str | None, optional
            Per-call override for ``--minAlertLevel``.

        Returns
        -------
        Sequence[ValeDiagnostic]
            Diagnostics reported for the synthetic ``<stdin>`` input.

        Raises
        ------
        ValeExecutionError
            Raised when Vale returns a runtime error (exit code ``>= 2``).

        """
        args = [
            "--no-global",
            "--no-exit",
            "--output=JSON",
            f"--ext={ext or self.stdin_ext}",
        ]
        if self._stdin_flag_supported:
            args.append("--stdin")
        level = min_alert_level or self.default_min_level
        if level is not None:
            args.append(f"--minAlertLevel={level}")
        output = self._run(args, stdin=text)
        by_file = _decode_vale_json(output)
        return next(iter(by_file.values()), [])

    def lint_path(
        self,
        path: Path,
        *,
        min_alert_level: str | None = None,
    ) -> dict[str, list[ValeDiagnostic]]:
        """Lint a file or directory path and group alerts by reported path.

        Parameters
        ----------
        path : Path
            Filesystem path to a single document or a directory tree.
        min_alert_level : str | None, optional
            Override for ``--minAlertLevel`` used in this invocation.

        Returns
        -------
        dict[str, list[ValeDiagnostic]]
            Mapping of Vale's reported path to emitted diagnostics.

        Raises
        ------
        ValeExecutionError
            Raised when Vale returns a runtime error (exit code ``>= 2``).

        """
        args = ["--no-global", "--no-exit", "--output=JSON"]
        level = min_alert_level or self.default_min_level
        if level is not None:
            args.append(f"--minAlertLevel={level}")
        output = self._run([*args, str(path)])
        return _decode_vale_json(output)

    def __enter__(self) -> Valedate:
        """Return self so the harness can act as a context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Clean up the sandbox when the context manager exits."""
        self.cleanup()

    def cleanup(self) -> None:
        """Remove the temporary working tree created for this harness."""
        self._tmp.cleanup()

    def _run(self, args: list[str], stdin: str | None = None) -> str:
        """Execute Vale with the provided arguments."""
        cmd = [self.vale_bin, f"--config={self.ini_path}", *args]
        proc = subprocess.run(  # noqa: S603
            cmd,
            cwd=self.root,
            input=stdin.encode("utf-8") if stdin is not None else None,
            capture_output=True,
            check=False,
        )
        if proc.returncode >= _VALE_RUNTIME_FAILURE_EXIT:
            stderr = proc.stderr.decode("utf-8", "replace")
            raise ValeExecutionError(proc.returncode, stderr)
        return proc.stdout.decode("utf-8", "replace")


__all__ = [
    "IniLike",
    "StylesLike",
    "ValeAction",
    "ValeBinaryNotFoundError",
    "ValeDiagnostic",
    "ValeExecutionError",
    "Valedate",
]
