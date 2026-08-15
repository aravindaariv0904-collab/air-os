"""
AirOS Engine — Bundled Resource Path Resolution
Resolves paths to bundled assets (models, configs) both in development
(running from the repo root) and in frozen executables (PyInstaller onedir,
where data files live under sys._MEIPASS / _internal).
"""

import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_path(rel_path: str) -> str:
    """
    Resolve a repository-relative path (e.g. 'assets/models/foo.task')
    against the correct base directory for the current environment.
    """
    rel_path = rel_path.replace("/", os.sep).replace("\\", os.sep)
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.join(base, rel_path)
    return os.path.join(_REPO_ROOT, rel_path)
