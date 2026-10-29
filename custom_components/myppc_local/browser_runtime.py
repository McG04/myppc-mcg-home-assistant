"""An on-demand browser dependency; no HA app, daemon or open network port."""
from pathlib import Path
import os
import platform
import shutil
import subprocess
import threading

_INSTALL_LOCK = threading.Lock()


class BrowserUnavailable(Exception):
    pass


def browser_binaries(directory):
    """Use existing binaries or build an isolated Alpine package root in /config.

    Only the package manager's already-trusted keys/repositories are used.
    Never installs packages into the Home Assistant Core filesystem.
    """
    chrome = shutil.which('chromium') or shutil.which('chromium-browser')
    driver = shutil.which('chromedriver')
    if chrome and driver:
        return chrome, driver
    root = Path(directory) / 'alpine-browser'
    chrome_wrapper, driver_wrapper = root / 'chrome.sh', root / 'driver.sh'
    with _INSTALL_LOCK:
        if chrome_wrapper.exists() and driver_wrapper.exists():
            return str(chrome_wrapper), str(driver_wrapper)
        apk = shutil.which('apk')
        if not apk or not Path('/etc/apk/keys').is_dir():
            raise BrowserUnavailable('Runtime-ul necesită Alpine/apk sau Chromium+chromedriver deja instalate')
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        (root / 'etc/apk').mkdir(parents=True, exist_ok=True)
        shutil.copytree('/etc/apk/keys', root / 'etc/apk/keys', dirs_exist_ok=True)
        shutil.copyfile('/etc/apk/repositories', root / 'etc/apk/repositories')
        result = subprocess.run([apk, '--root', str(root), '--initdb', '--no-cache',
            '--no-scripts', '--no-progress', 'add', 'chromium', 'chromium-chromedriver'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900, check=False)
        if result.returncode:
            raise BrowserUnavailable('Nu s-au putut instala dependențele browserului în directorul integrării')
        arch = {'aarch64':'aarch64', 'arm64':'aarch64', 'x86_64':'x86_64'}.get(platform.machine())
        if not arch:
            raise BrowserUnavailable('Arhitectură nesuportată')
        loader = root / f'lib/ld-musl-{arch}.so.1'
        if not loader.exists():
            raise BrowserUnavailable('Lipsește loader-ul Alpine')
        binaries = [root/'usr/lib/chromium/chromium', root/'usr/bin/chromedriver']
        if not all(p.exists() for p in binaries):
            raise BrowserUnavailable('Pachetul Chromium nu are structura așteptată')
        # Use Core's Alpine ELF loader while resolving browser libraries only
        # from the isolated root. Direct exec also keeps /proc/self/exe correct
        # for Chromium's renderer/crashpad subprocesses.
        icu_dirs = [p for p in (root/'usr/share/icu').glob('*') if p.is_dir()]
        icu_data = icu_dirs[0] if len(icu_dirs)==1 else root/'usr/share/icu'
        for wrapper, binary in zip((chrome_wrapper, driver_wrapper), binaries):
            content = ('#!/bin/sh\n'
                       f'export LD_LIBRARY_PATH="{root}/usr/lib:{root}/lib"\n'
                       f'export ICU_DATA="{icu_data}"\n'
                       f'export FONTCONFIG_PATH="{root}/etc/fonts"\n'
                       f'export XDG_DATA_DIRS="{root}/usr/share"\n'
                       f'exec "{binary}" "$@"\n')
            temporary = wrapper.with_suffix('.tmp')
            temporary.write_text(content)
            temporary.chmod(0o700)
            temporary.replace(wrapper)
        return str(chrome_wrapper), str(driver_wrapper)
