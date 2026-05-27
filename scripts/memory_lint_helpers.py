#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Memory Lint Helpers — Common patterns and utilities.

STATUS: PARTIALLY INTEGRATED.

The classes ``RegexPatterns`` / ``CheckResultHandler`` / ``SafeFileOperations``
/ ``FrontmatterExtractor`` / ``ValidationHelpers`` are still preparatory
infrastructure for splitting the monolithic ``MemoryLint`` class in
``memory_lint.py``; their full integration is tracked under the
"Integrate memory_lint_helpers.py during MemoryLinter split" GitHub issue
(#11).

The ``EncodingGate`` class is *production* code — it is consumed by
``memory_lint.py``'s ``--validate-encoding`` mode and (via importing
this module) by the hot-memory write hooks ``auto-remember.py`` /
``precompact-flush-l4.py``. Its job is to fail loudly when a hook
would otherwise silently corrupt ``handoff.md`` with cp1251-as-utf8
mojibake.

The classes below are re-exported via ``__all__`` so static analysers and
dead-code linters (vulture, pylint W0611) understand they are part of
the public surface, not stale private helpers.
"""

import re
from pathlib import Path
from typing import Any, Callable, List, Optional

__all__ = [
    "RegexPatterns",
    "CheckResultHandler",
    "SafeFileOperations",
    "FrontmatterExtractor",
    "ValidationHelpers",
    "EncodingGate",
    "EncodingError",
]


class RegexPatterns:
    """Compiled regex patterns for better performance"""

    # Frontmatter extraction
    FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

    # Link patterns
    LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^\)]+)\)")
    MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\(([^\)]+\.md)\)")

    # Frontmatter field patterns
    FIELD_NAME = re.compile(r"^name:\s*(.+)$", re.MULTILINE)
    FIELD_DESCRIPTION = re.compile(r"^description:\s*(.+)$", re.MULTILINE)
    FIELD_TYPE = re.compile(r"^type:\s*(.+)$", re.MULTILINE)

    # Date patterns
    DATE_PATTERN = re.compile(r"\b(20\d{2}[-/]\d{2}[-/]\d{2})\b")

    # Special characters for sanitization
    SPECIAL_CHARS = re.compile(r"[^\w\s\-.,!?]")


class CheckResultHandler:
    """Handler for check results with consistent formatting"""

    def __init__(self, reporter):
        """
        Initialize handler with reporter instance

        Args:
            reporter: BaseReporter instance for output
        """
        self.reporter = reporter

    def handle_check_result(
        self, results: List[Any], check_name: str, show_details: bool = True
    ) -> List[Any]:
        """
        Handle check results with consistent formatting

        Args:
            results: List of check results
            check_name: Name of the check
            show_details: Whether to show detailed results

        Returns:
            Original results list
        """
        self.reporter.print_section(check_name)

        if results:
            self.reporter.print_warn(f"Found {len(results)} issue(s)")
            if show_details:
                for result in results:
                    self.reporter.print_info(f"  {result}")
        else:
            self.reporter.print_ok("No issues found")

        return results

    def handle_check_dict_result(
        self, results: List[dict], check_name: str, key_field: str = "file"
    ) -> List[dict]:
        """
        Handle dictionary check results

        Args:
            results: List of dict results
            check_name: Name of the check
            key_field: Field to use as primary identifier

        Returns:
            Original results list
        """
        self.reporter.print_section(check_name)

        if results:
            self.reporter.print_warn(f"Found {len(results)} issue(s)")
            for result in results:
                key = result.get(key_field, "unknown")
                message = result.get("message", str(result))
                self.reporter.print_info(f"  {key}: {message}")
        else:
            self.reporter.print_ok("No issues found")

        return results


class SafeFileOperations:
    """Safe file operations with error handling"""

    def __init__(self, reporter):
        """
        Initialize with reporter for warnings

        Args:
            reporter: BaseReporter instance for output
        """
        self.reporter = reporter

    def safe_file_operation(
        self, file_path: Path, operation: Callable[[Path], Any], default: Any = None
    ) -> Any:
        """
        Execute file operation with error handling

        Args:
            file_path: Path to file
            operation: Function to execute on file
            default: Default value on error

        Returns:
            Operation result or default on error
        """
        try:
            return operation(file_path)
        except PermissionError:
            self.reporter.print_warn(f"Permission denied: {file_path}")
            return default
        except FileNotFoundError:
            self.reporter.print_warn(f"File not found: {file_path}")
            return default
        except Exception as exc:
            self.reporter.print_warn(f"Error processing {file_path}: {exc}")
            return default

    def safe_read_text(self, file_path: Path, encoding: str = "utf-8") -> str:
        """
        Safely read file text

        Args:
            file_path: Path to file
            encoding: Text encoding

        Returns:
            File content or empty string on error
        """
        return self.safe_file_operation(
            file_path, lambda p: p.read_text(encoding=encoding), default=""
        )

    def safe_read_bytes(self, file_path: Path) -> bytes:
        """
        Safely read file bytes

        Args:
            file_path: Path to file

        Returns:
            File content or empty bytes on error
        """
        return self.safe_file_operation(
            file_path, lambda p: p.read_bytes(), default=b""
        )

    def safe_stat(self, file_path: Path) -> Optional[Any]:
        """
        Safely get file stats

        Args:
            file_path: Path to file

        Returns:
            File stats or None on error
        """
        return self.safe_file_operation(file_path, lambda p: p.stat(), default=None)


class FrontmatterExtractor:
    """Extract and parse frontmatter from markdown files"""

    @staticmethod
    def extract_frontmatter(content: str) -> dict:
        """
        Extract YAML frontmatter from markdown content

        Args:
            content: Markdown file content

        Returns:
            Dictionary with frontmatter fields
        """
        match = RegexPatterns.FRONTMATTER.match(content)
        if not match:
            return {}

        frontmatter_text = match.group(1)
        result = {}

        # Extract common fields
        if name_match := RegexPatterns.FIELD_NAME.search(frontmatter_text):
            result["name"] = name_match.group(1).strip()

        if desc_match := RegexPatterns.FIELD_DESCRIPTION.search(frontmatter_text):
            result["description"] = desc_match.group(1).strip()

        if type_match := RegexPatterns.FIELD_TYPE.search(frontmatter_text):
            result["type"] = type_match.group(1).strip()

        return result

    @staticmethod
    def extract_links(content: str) -> List[str]:
        """
        Extract markdown links from content

        Args:
            content: Markdown content

        Returns:
            List of link targets
        """
        links = []
        for match in RegexPatterns.LINK_PATTERN.finditer(content):
            link = match.group(2)
            # Skip external links and anchors
            if not link.startswith(("http://", "https://", "#")):
                links.append(link)
        return links


class ValidationHelpers:
    """Common validation helpers"""

    @staticmethod
    def is_valid_memory_type(memory_type: str) -> bool:
        """
        Check if memory type is valid

        Args:
            memory_type: Type string to validate

        Returns:
            True if valid type
        """
        valid_types = {"user", "feedback", "project", "reference"}
        return memory_type.lower() in valid_types

    @staticmethod
    def sanitize_input(text: str) -> str:
        """
        Sanitize user input by removing special characters

        Args:
            text: Input text

        Returns:
            Sanitized text
        """
        return RegexPatterns.SPECIAL_CHARS.sub("", text)

    @staticmethod
    def extract_dates(content: str) -> List[str]:
        """
        Extract dates from content

        Args:
            content: Text content

        Returns:
            List of date strings
        """
        return RegexPatterns.DATE_PATTERN.findall(content)


class EncodingError(ValueError):
    """Raised when text written to a memory file would corrupt it.

    Subclass of ``ValueError`` so callers that already catch
    ``ValueError`` (e.g. broad input-validation handlers) get
    consistent behaviour, but specific enough that hot-memory write
    hooks can target it precisely.
    """


class EncodingGate:
    """Comprehensive encoding validation and cleanup for UTF-8 memory files.

    Hot-memory hooks (``auto-remember.py``, ``precompact-flush-l4.py``)
    collect output from sub-processes
    (``git log``, PowerShell, etc.) and append it to ``handoff.md`` /
    ``decisions.md``. On Windows the sub-process default codepage is
    often ``cp1251`` (Cyrillic Windows), and naive concatenation of
    those bytes into a UTF-8 file produces *mojibake* — a sequence of
    Latin-1-looking characters that decodes to garbage when the next
    Claude session reads the file. The user-visible symptom is
    "the agent forgets what we did".

    This class provides two categories of functionality:

    **Validation (for hooks writing to memory files):**

    1. ``assert_clean(text)`` — Refuses any text containing the Unicode
       replacement character ``U+FFFD`` (definitive evidence of a prior
       decode failure).
    2. Heuristically flags cp1251-encoded Cyrillic that has been
       round-tripped through ``latin-1.encode -> utf-8.decode``
       — the canonical mojibake pattern from Windows shells.
    3. ``assert_clean_bytes(data)`` — Refuses bytes that don't decode
       as UTF-8 at all.

    **Cleanup (for repairing corrupted files):**

    4. ``strip_bom(data)`` — Removes Byte Order Mark (UTF-8, UTF-16 LE/BE).
    5. ``strip_control_chars(data)`` — Removes null bytes and control
       characters (except newline/CR).
    6. ``repair_mojibake(text)`` — Attempts to invert cp1251-as-utf8
       mojibake via round-trip decoding.
    7. ``clean_file(path)`` — Comprehensive file cleanup combining all
       of the above operations.

    The gate is deliberately conservative: it false-positives on
    pathological-but-legitimate Latin-1 content (e.g. raw German /
    French quoted-printable inside markdown). Hooks should call it
    on text *they* produced from sub-shells, not on user-authored
    free text.

    Examples:
        >>> # Validation in hooks
        >>> text = subprocess.check_output(['git', 'log']).decode('utf-8')
        >>> EncodingGate.assert_clean(text, source="git log")

        >>> # Cleanup corrupted file
        >>> from pathlib import Path
        >>> changed, changes = EncodingGate.clean_file(Path("handoff.md"))
        >>> if changed:
        ...     print(f"Fixed: {', '.join(changes)}")
    """

    REPLACEMENT_CHAR = "\ufffd"

    # cp1251-as-utf8 mojibake signature.
    #
    # Russian / Bulgarian / Ukrainian text in UTF-8 is always two bytes
    # per character, with the first byte in {0xD0, 0xD1}. When such
    # bytes are mistakenly interpreted as cp1251 they render as
    # ``Р`` (0xD0) or ``С`` (0xD1), each followed by some Latin-1
    # glyph that came from the second UTF-8 byte (0x80..0xBF).
    #
    # The signature is therefore any occurrence of ``Р`` or ``С``
    # followed by a Latin-1 supplement character in the range
    # U+0080..U+00BF. Normal Russian text never produces this pair,
    # because a Cyrillic ``Р`` / ``С`` is followed by another
    # Cyrillic letter, never by a Latin-1 punctuation glyph.
    _MOJIBAKE_RE = re.compile(r"[\u0420\u0421][\u0080-\u00bf]")

    @classmethod
    def assert_clean(cls, text: str, *, source: str = "<unknown>") -> None:
        """Raise ``EncodingError`` if ``text`` contains UTF-8 corruption.

        Args:
            text: The fully-decoded string that a hook intends to
                write to a memory file.
            source: Human-readable label for the producer of the
                text (e.g. ``"git log subprocess"``). Echoed in the
                error message so the failing hook is easy to find.

        Raises:
            EncodingError: If ``text`` contains the Unicode
                replacement character or known mojibake trigraphs.
        """
        if cls.REPLACEMENT_CHAR in text:
            raise EncodingError(
                f"Text from {source} contains the Unicode replacement "
                f"character (U+FFFD). This is definitive evidence that "
                f"some earlier decode failed; refusing to write garbled "
                f"data to a UTF-8 memory file."
            )

        match = cls._MOJIBAKE_RE.search(text)
        if match is not None:
            raise EncodingError(
                f"Text from {source} contains the mojibake pair "
                f"{match.group(0)!r}, which is the cp1251-as-utf8 "
                f"signature produced when sub-process output is "
                f"concatenated into a UTF-8 file without re-decoding. "
                f"Re-decode the sub-process output explicitly, e.g. "
                f"``proc.stdout.decode('cp1251').encode('utf-8')``."
            )

        # Broader detector for the common case where every cp1251
        # second byte decodes to a Cyrillic-block glyph (U+0400..U+04FF)
        # rather than a Latin-1 supplement char. Words like "история",
        # "город", "мир" produce mojibake whose pairs are entirely
        # outside U+0080..U+00BF, so the strict regex misses them.
        #
        # ``_MOJIBAKE_RUN_RE`` alone over-matches on legitimate Russian
        # uppercase patterns like "СССР" or "РОССИЯ". To eliminate
        # those false positives we additionally require that the
        # cp1251 round-trip (``chunk.encode('cp1251').decode('utf-8')``)
        # actually recovers a clean UTF-8 string — the same evidence
        # ``repair_mojibake`` uses to confirm a chunk is repairable.
        # Real mojibake round-trips cleanly; legitimate text fails
        # the round-trip because the source bytes don't form valid
        # UTF-8 sequences.
        run_match = cls._MOJIBAKE_RUN_RE.search(text)
        if run_match is not None and cls._is_repairable_run(run_match.group(0)):
            raise EncodingError(
                f"Text from {source} contains a cp1251-as-utf8 mojibake "
                f"run {run_match.group(0)!r}. This indicates sub-process "
                f"output was concatenated into a UTF-8 file without "
                f"re-decoding. Re-decode the sub-process output "
                f"explicitly, e.g. "
                f"``proc.stdout.decode('cp1251').encode('utf-8')``."
            )

    @classmethod
    def assert_clean_bytes(
        cls,
        data: bytes,
        *,
        source: str = "<unknown>",
    ) -> str:
        """Decode ``data`` as UTF-8 and run ``assert_clean`` on the result.

        Args:
            data: Bytes about to be decoded for a memory file.
            source: Producer label for diagnostics.

        Returns:
            The successfully-decoded UTF-8 string.

        Raises:
            EncodingError: If ``data`` is not valid UTF-8, or if the
                decoded string fails ``assert_clean``.
        """
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EncodingError(
                f"Bytes from {source} are not valid UTF-8 "
                f"(byte {exc.start} of {len(data)}: {exc.reason}). "
                f"Likely cp1251 / cp866 / latin-1 from a Windows "
                f"sub-process; decode with the producer's codepage "
                f"first, then encode as UTF-8 before writing to a "
                f"memory file."
            ) from exc
        cls.assert_clean(text, source=source)
        return text

    # Boundary regex used to find chunks of mojibake within a larger
    # mostly-clean file. A chunk is ≥ 2 consecutive pairs of
    # ``(Cyrillic Р|С) + (cp1251-high-byte glyph)``. The set of
    # cp1251-high-byte glyphs is broader than U+0080..U+00BF — it
    # includes Cyrillic letters (cp1251 0xC0..0xFF), Cyrillic
    # supplementary glyphs (e.g. ``ј`` = U+0458 from cp1251 0xBC),
    # and the General Punctuation block (e.g. ``„`` = U+201E from
    # cp1251 0x84). We compute the set programmatically once at
    # class-load time so it stays in sync with Python's cp1251 codec.
    _CP1251_HIGH_GLYPHS = "".join(
        sorted(
            {
                bytes([b]).decode("cp1251")
                for b in range(0x80, 0x100)
                if b != 0x98  # cp1251 0x98 has no defined mapping
            }
        )
    )
    _MOJIBAKE_RUN_RE = re.compile(
        r"(?:[\u0420\u0421][" + re.escape(_CP1251_HIGH_GLYPHS) + r"]){2,}"
    )

    @classmethod
    def _is_repairable_run(cls, chunk: str) -> bool:
        """Return True iff ``chunk`` round-trips through cp1251 to clean UTF-8.

        Used as the false-positive filter for ``_MOJIBAKE_RUN_RE``
        matches in ``assert_clean`` and ``scan_file``. A chunk is
        considered real mojibake (and thus worth flagging) only if:

        1. ``chunk.encode('cp1251')`` succeeds (Python's cp1251 codec
           covers every char in ``_CP1251_HIGH_GLYPHS`` by construction,
           plus the Cyrillic block, so this almost always succeeds).
        2. The resulting bytes decode as valid UTF-8.
        3. The recovered text contains no replacement char and no
           strict-signature mojibake pair, i.e. recovery is complete.

        Legitimate uppercase Russian patterns like "СССР" /
        "РОССИЯ" / "СИСТЕМА" match the broader regex shape but fail
        step 2 (their cp1251 byte sequences aren't valid UTF-8), so
        they're not flagged.
        """
        try:
            recovered = chunk.encode("cp1251").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return False
        if cls.REPLACEMENT_CHAR in recovered:
            return False
        if cls._MOJIBAKE_RE.search(recovered) is not None:
            return False
        return True

    @classmethod
    def repair_mojibake(cls, text: str) -> "tuple[str, bool]":
        """Attempt to invert cp1251-as-utf8 mojibake on ``text``.

        Mojibake here means: original bytes were valid UTF-8 (e.g.
        Cyrillic letters, em-dashes); some intermediate process
        treated those bytes as cp1251 and re-encoded the result as
        UTF-8. The round-trip
        ``chunk.encode('cp1251').decode('utf-8')`` recovers the
        original bytes exactly.

        ``text`` is typically a whole memory file, where only some
        regions are corrupted (e.g. ``handoff.md`` keeps clean
        markdown headers and clean Cyrillic captions interleaved
        with mojibake'd subprocess output). We therefore locate
        contiguous runs of mojibake with ``_MOJIBAKE_RUN_RE`` and
        repair each run independently; the rest of the text passes
        through unchanged.

        A run is considered repaired only when:

        1. The cp1251 round-trip on the run succeeds.
        2. The recovered text still decodes as UTF-8 (it does, by
           construction of the codec).
        3. The recovered text no longer contains the strict
           cp1251-as-utf8 signature ``[Р|С] + latin-1-supplement``
           (the unambiguous mojibake marker).

        Args:
            text: The (possibly partially) corrupted string read from
                a memory file.

        Returns:
            A tuple ``(result, is_repairable)``:

            * ``is_repairable=True`` and ``result`` differs from
              ``text``: at least one mojibake run was successfully
              recovered.
            * ``is_repairable=False`` and ``result == text``: no
              mojibake runs were found, or every run failed to round-
              trip (file may be double-encoded; manual review).
        """
        any_changed = False

        def _repair_run(match: "re.Match[str]") -> str:
            nonlocal any_changed
            chunk = match.group(0)
            try:
                recovered = chunk.encode("cp1251").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return chunk
            if cls.REPLACEMENT_CHAR in recovered:
                return chunk
            # Strict signature check: the *unambiguous* mojibake marker
            # (Р|С followed by a Latin-1 supplement char). Plain
            # Cyrillic ``Ре``, ``Ро``, ``Се`` is not flagged because
            # ``е``/``о`` live in U+0400..U+04FF, not U+0080..U+00BF.
            if cls._MOJIBAKE_RE.search(recovered) is not None:
                return chunk
            any_changed = True
            return recovered

        result = cls._MOJIBAKE_RUN_RE.sub(_repair_run, text)
        return (result, any_changed) if any_changed else (text, False)

    @classmethod
    def scan_file(cls, path: Path) -> Optional[str]:
        """Return a human-readable issue if ``path`` already contains mojibake.

        Args:
            path: Path to a memory markdown file.

        Returns:
            ``None`` if the file is clean (or unreadable for an
            unrelated reason), otherwise a short message describing
            what was found. Used by ``memory_lint --validate-encoding``
            to enumerate already-corrupted files without raising.
        """
        try:
            data = path.read_bytes()
        except OSError:
            return None
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            return (
                f"not valid UTF-8 (byte {exc.start} of {len(data)}: " f"{exc.reason})"
            )
        if cls.REPLACEMENT_CHAR in text:
            return "contains Unicode replacement character (U+FFFD)"
        match = cls._MOJIBAKE_RE.search(text)
        if match is not None:
            return f"contains cp1251-as-utf8 mojibake pair {match.group(0)!r}"
        # Broader detector mirroring ``assert_clean``: catch mojibake
        # runs whose second byte decodes to a Cyrillic-block glyph
        # rather than a Latin-1 supplement (covers "история", "город",
        # "мир", etc.). The cp1251 round-trip check filters out
        # legitimate Russian uppercase patterns ("СССР", "РОССИЯ")
        # that match the broader regex shape but don't actually
        # decode back to clean UTF-8.
        run_match = cls._MOJIBAKE_RUN_RE.search(text)
        if run_match is not None and cls._is_repairable_run(run_match.group(0)):
            return f"contains cp1251-as-utf8 mojibake run {run_match.group(0)!r}"
        return None

    @classmethod
    def strip_bom(cls, data: bytes) -> tuple[bytes, Optional[str]]:
        """Remove Byte Order Mark (BOM) from bytes.

        Args:
            data: Raw bytes that may contain a BOM prefix.

        Returns:
            A tuple ``(cleaned_data, bom_type)``:

            * ``cleaned_data``: bytes with BOM removed if present,
              otherwise original data.
            * ``bom_type``: "UTF-8", "UTF-16-LE", "UTF-16-BE", or
              ``None`` if no BOM was found.

        Examples:
            >>> data = b'\\xef\\xbb\\xbfHello'
            >>> cleaned, bom = EncodingGate.strip_bom(data)
            >>> cleaned
            b'Hello'
            >>> bom
            'UTF-8'
        """
        if data.startswith(b"\xef\xbb\xbf"):
            return (data[3:], "UTF-8")
        if data.startswith(b"\xff\xfe"):
            return (data[2:], "UTF-16-LE")
        if data.startswith(b"\xfe\xff"):
            return (data[2:], "UTF-16-BE")
        return (data, None)

    @classmethod
    def strip_control_chars(cls, data: bytes) -> tuple[bytes, int]:
        """Remove null bytes and control characters from bytes.

        Removes:
        - Null bytes (0x00)
        - Control characters (0x01-0x1F) except newline (0x0A) and
          carriage return (0x0D)

        Args:
            data: Raw bytes to clean.

        Returns:
            A tuple ``(cleaned_data, removed_count)``:

            * ``cleaned_data``: bytes with control chars removed.
            * ``removed_count``: number of bytes removed.

        Examples:
            >>> data = b'Hello\\x00World\\x01'
            >>> cleaned, count = EncodingGate.strip_control_chars(data)
            >>> cleaned
            b'HelloWorld'
            >>> count
            2
        """
        cleaned = bytearray()
        removed = 0
        for byte in data:
            if byte == 0x00:  # null byte
                removed += 1
                continue
            if byte < 0x20 and byte not in (0x0A, 0x0D):  # control chars
                removed += 1
                continue
            cleaned.append(byte)
        return (bytes(cleaned), removed)

    @classmethod
    def clean_file(
        cls,
        path: Path,
        *,
        repair_mojibake: bool = True,
        strip_bom: bool = True,
        strip_control: bool = True,
    ) -> tuple[bool, list[str]]:
        """Comprehensive file cleanup: BOM + control chars + mojibake.

        Performs a multi-stage cleanup:

        1. Strip BOM if present (UTF-8, UTF-16 LE/BE).
        2. Remove null bytes and control characters.
        3. Decode as UTF-8 (with ``errors='replace'`` fallback).
        4. Repair cp1251-as-utf8 mojibake if requested.
        5. Write cleaned content back to disk.

        Args:
            path: Path to the file to clean.
            repair_mojibake: Whether to attempt mojibake repair
                (default: True).
            strip_bom: Whether to remove BOM (default: True).
            strip_control: Whether to remove control chars
                (default: True).

        Returns:
            A tuple ``(changed, changes)``:

            * ``changed``: ``True`` if any modifications were made.
            * ``changes``: List of human-readable change descriptions
              (e.g. ``["BOM (UTF-8) removed", "Mojibake repaired"]``).

        Raises:
            OSError: If the file cannot be read or written.

        Examples:
            >>> path = Path("corrupted.md")
            >>> changed, changes = EncodingGate.clean_file(path)
            >>> if changed:
            ...     print(f"Fixed: {', '.join(changes)}")
        """
        changes: list[str] = []

        # Read raw bytes
        data = path.read_bytes()
        len(data)

        # 1. Strip BOM
        if strip_bom:
            data, bom_type = cls.strip_bom(data)
            if bom_type is not None:
                changes.append(f"BOM ({bom_type}) removed")

        # 2. Strip control chars
        if strip_control:
            data, removed_count = cls.strip_control_chars(data)
            if removed_count > 0:
                changes.append(f"Control chars removed ({removed_count} bytes)")

        # 3. Decode as UTF-8 (with fallback)
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            # Fallback: replace invalid sequences
            text = data.decode("utf-8", errors="replace")
            changes.append("Invalid UTF-8 replaced with U+FFFD")

        # 4. Repair mojibake
        mojibake_repaired = False
        if repair_mojibake:
            text, mojibake_repaired = cls.repair_mojibake(text)
            if mojibake_repaired:
                changes.append("Mojibake repaired")

        # 5. Write back if changed
        if changes:
            path.write_bytes(text.encode("utf-8"))

        return (bool(changes), changes)
