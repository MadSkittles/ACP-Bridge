from __future__ import annotations

import ntpath
import os
from pathlib import Path


def is_path_allowed(path: str, allowed_roots: list[str], *, platform: str | None = None) -> bool:
    platform_name = (platform or os.name).lower()
    if platform_name in {"windows", "nt"}:
        return _is_windows_path_allowed(path, allowed_roots)
    return _is_posix_path_allowed(path, allowed_roots)


def _is_windows_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    if not ntpath.isabs(path):
        return False
    candidate = ntpath.normcase(ntpath.normpath(path))
    for root in allowed_roots:
        if not ntpath.isabs(root):
            continue
        normalized_root = ntpath.normcase(ntpath.normpath(root))
        try:
            if ntpath.commonpath([candidate, normalized_root]) == normalized_root:
                return True
        except ValueError:
            continue
    return False


def _is_posix_path_allowed(path: str, allowed_roots: list[str]) -> bool:
    candidate = Path(path)
    if not candidate.is_absolute():
        return False
    candidate_resolved = candidate.resolve(strict=False)
    for root in allowed_roots:
        root_path = Path(root)
        if not root_path.is_absolute():
            continue
        try:
            candidate_resolved.relative_to(root_path.resolve(strict=False))
            return True
        except ValueError:
            continue
    return False
