"""
paths.py — Runtime path resolution.

Works both in development (plain Python) and when frozen by PyInstaller.
"""
import os
import sys


def get_templates_dir() -> str:
    """Return absolute path to the assets directory (formerly Templates)."""
    if getattr(sys, "frozen", False):
        # PyInstaller exe: assets folder sits next to the .exe
        return os.path.join(os.path.dirname(sys.executable), "assets")
    # Development: paths.py lives at tools/exporter/ — go up 3 levels to project root
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "assets",
    )
