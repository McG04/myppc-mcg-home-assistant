"""Resolve or provision a private Chromium runtime."""
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from threading import Lock

_INSTALL_LOCK = Lock()
_CHROME = Path("usr/lib/chromium/chromium")
_DRIVER = Path("usr/bin/chromedriver")


class BrowserUnavailable(Exception):
    """Chromium or its matching driver is not available in the HA environment."""


def browser_binaries(runtime=None):
    """Use a system pair or provision matching Alpine packages under runtime."""
    chrome = shutil.which("chromium") or shutil.which("chromium-browser")
    driver = shutil.which("chromedriver")
    if chrome and driver:
        return chrome, driver, None

    if runtime is not None:
        root = Path(runtime) / "alpine-browser"
        with _INSTALL_LOCK:
            if not root.exists():
                _provision(root)
        chrome = root / _CHROME
        driver = root / _DRIVER
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
        "Consultă instrucțiunile din README."
    )

def _provision(root):
    """Install signed Alpine packages into a private directory before publishing it."""
    apk = shutil.which("apk")
    config = Path("/etc/apk")
    if not apk or not (config / "keys").is_dir() or not (config / "repositories").is_file():
        return

    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="alpine-browser-", dir=root.parent) as directory:
            staging = Path(directory) / "root"
            staging_config = staging / "etc/apk"
            staging_config.mkdir(parents=True, mode=0o700)
            shutil.copytree(config / "keys", staging_config / "keys")
            shutil.copyfile(config / "repositories", staging_config / "repositories")
            subprocess.run(
                [apk, "--root", str(staging), "--initdb", "--no-cache",
                 "--no-scripts", "--no-progress", "add", "chromium", "chromium-chromedriver"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=900,
                check=True,
            )
            if not all(path.is_file() and os.access(path, os.X_OK)
                       for path in (staging / _CHROME, staging / _DRIVER)):
                raise BrowserUnavailable("Pachetele Alpine nu conțin executabilele așteptate.")
            staging.rename(root)
    except (OSError, subprocess.SubprocessError) as err:
        raise BrowserUnavailable("Instalarea runtime-ului Chromium din Alpine a eșuat.") from err
