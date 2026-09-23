"""Directory ingestion: walk input dir, hash files, detect duplicates.

Duplicates are detected by SHA-256 of file bytes (exact-file duplicates).
Per the requirements, duplicates are never silently discarded — every
duplicate file is still processed and represented in the output, with
`is_duplicate`/`duplicate_of` set so a reviewer can see what happened.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass


@dataclass
class IngestedFile:
    path: str
    filename: str
    sha256: str
    is_duplicate: bool = False
    duplicate_of: str | None = None


SUPPORTED_EXTENSIONS = (".pdf", ".docx")


def ingest_directory(input_dir: str) -> list[IngestedFile]:
    """Return every supported resume file in `input_dir`, sorted by name,
    with duplicate detection via content hash. Non-resume files are skipped."""
    if not os.path.isdir(input_dir):
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    filenames = sorted(
        f for f in os.listdir(input_dir)
        if f.lower().endswith(SUPPORTED_EXTENSIONS)
    )

    seen_hashes: dict[str, str] = {}  # sha256 -> first filename seen
    files: list[IngestedFile] = []

    for filename in filenames:
        path = os.path.join(input_dir, filename)
        try:
            with open(path, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
        except Exception as e:  # noqa: BLE001
            # Unreadable file (permissions, locked, etc). Represent it with an
            # empty-ish hash so it still surfaces downstream as a parse failure
            # rather than disappearing silently.
            files.append(IngestedFile(path=path, filename=filename, sha256=f"UNREADABLE:{e}"))
            continue

        is_dup = digest in seen_hashes
        dup_of = seen_hashes.get(digest)
        if not is_dup:
            seen_hashes[digest] = filename

        files.append(
            IngestedFile(
                path=path,
                filename=filename,
                sha256=digest,
                is_duplicate=is_dup,
                duplicate_of=dup_of,
            )
        )

    return files
