"""Entry point — pick the platform implementation and run.  ``python -m voice_wheel``"""

from __future__ import annotations

import sys


def main():
    if sys.platform == "darwin":
        from .platform.macos.macos_app import main as run
        return run()
    raise SystemExit(
        f"Платформа {sys.platform!r} пока не поддерживается (есть только macOS)."
    )


if __name__ == "__main__":
    raise SystemExit(main())
