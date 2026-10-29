import os
import shutil
import subprocess  # noqa: S404  (fixed argv, no shell, controlled environment)
import tempfile
from pathlib import Path

from apps.draws.ingestion.extractors.base import (
    SUBPROCESS_TIMEOUT,
    ExtractedText,
    ExtractionError,
    ExtractorUnavailable,
)
from apps.draws.ingestion.extractors.txt import extract_txt


def find_soffice() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def extract_doc(data: bytes, timeout: int = SUBPROCESS_TIMEOUT) -> ExtractedText:
    """Convert a legacy .doc with headless LibreOffice in a throw-away directory.

    The converter runs with a fixed argv (no shell), a scrubbed environment, its own profile directory and a hard
    timeout. It is never given a network address to open.
    """
    soffice = find_soffice()
    if soffice is None:
        raise ExtractorUnavailable("LibreOffice (soffice) is not installed")
    with tempfile.TemporaryDirectory(prefix="draws-doc-") as workdir:
        source = Path(workdir) / "input.doc"
        source.write_bytes(data)
        profile = Path(workdir) / "profile"
        argv = [
            soffice,
            f"-env:UserInstallation={profile.as_uri()}",
            "--headless",
            "--norestore",
            "--convert-to",
            "txt:Text",
            "--outdir",
            str(workdir),
            str(source),
        ]
        env = {"PATH": os.environ.get("PATH", ""), "HOME": workdir, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")}
        try:
            subprocess.run(argv, check=True, capture_output=True, timeout=timeout, env=env, cwd=workdir)  # noqa: S603
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(f"LibreOffice timed out after {timeout}s") from exc
        except subprocess.CalledProcessError as exc:
            raise ExtractionError(f"LibreOffice failed with exit code {exc.returncode}") from exc
        output = Path(workdir) / "input.txt"
        if not output.exists():
            raise ExtractionError("LibreOffice produced no output")
        result = extract_txt(output.read_bytes())
    return ExtractedText(text=result.text, method="DOC_CONVERT", warnings=result.warnings)
