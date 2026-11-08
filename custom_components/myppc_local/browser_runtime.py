"""Find operator-provided browser binaries without installing software."""
import os
from pathlib import Path
import shutil


class BrowserUnavailable(Exception):
    """Chromium or its matching driver is not available in the HA environment."""


def browser_binaries(runtime=None):
    """Resolve existing executables from PATH; never download or create binaries."""
    chrome = shutil.which("chromium") or shutil.which("chromium-browser")
    driver = shutil.which("chromedriver")
    if chrome and driver:
        return chrome, driver, None

    if runtime is not None:
        root = Path(runtime) / "alpine-browser"
        chrome = root / "usr/lib/chromium/chromium"
        driver = root / "usr/bin/chromedriver"
        if all(path.is_file() and os.access(path, os.X_OK) for path in (chrome, driver)):
            icu_root = root / "usr/share/icu"
            icu_dirs = [path for path in icu_root.glob("*") if path.is_dir()]
            env = {
                **os.environ,
                "LD_LIBRARY_PATH": os.pathsep.join(map(str, (root / "usr/lib", root / "lib"))),
                "ICU_DATA": str(icu_dirs[0] if len(icu_dirs) == 1 else icu_root),
                "FONTCONFIG_PATH": str(root / "etc/fonts"),
                "XDG_DATA_DIRS": str(root / "usr/share"),
            }
            return str(chrome), str(driver), env

    raise BrowserUnavailable(
        "Chromium și chromedriver lipsesc din PATH și din runtime-ul local existent. "
        "Integrarea nu instalează pachete. Consultă instrucțiunile din README."
    )
