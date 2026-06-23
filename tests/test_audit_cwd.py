import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit import PreInstallAudit


def test_save_report_writes_to_claude_dir(tmp_path, monkeypatch):
    """save_report() should write to ~/.claude/, not CWD."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    audit = PreInstallAudit()
    audit.stats = {"test": True}

    audit.save_report()

    report_in_cwd = tmp_path / "pre_install_audit_report.json"
    report_in_claude = tmp_path / ".claude" / "pre_install_audit_report.json"

    assert not report_in_cwd.exists(), (
        "save_report() should NOT write to CWD"
    )
    assert report_in_claude.exists(), (
        "save_report() should write to ~/.claude/"
    )


def test_save_report_returns_path(tmp_path, monkeypatch):
    """save_report() should return the path to the report file."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    audit = PreInstallAudit()
    audit.stats = {"test": True}

    result = audit.save_report()

    assert result is not None
    assert Path(result).name == "pre_install_audit_report.json"
    assert ".claude" in str(Path(result).parent)
