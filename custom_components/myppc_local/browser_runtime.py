"""Find operator-provided browser binaries without installing software."""
import shutil


class BrowserUnavailable(Exception):
    """Chromium or its matching driver is not available in the HA environment."""


def browser_binaries():
    """Resolve existing executables from PATH; never download or create binaries."""
    chrome = shutil.which("chromium") or shutil.which("chromium-browser")
    driver = shutil.which("chromedriver")
    if not chrome or not driver:
        raise BrowserUnavailable(
            "Chromium și chromedriver trebuie instalate în prealabil de administrator "
            "în mediul în care rulează Home Assistant și disponibile în PATH. "
            "Integrarea nu instalează pachete. Consultă instrucțiunile din README."
        )
    return chrome, driver
