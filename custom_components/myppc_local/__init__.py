"""Native HA integration with one daily portal check and an internal login browser."""
import json
import logging
from pathlib import Path
import threading
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .daily import DailyGate
from .portal import Portal, LoginRequired
from .browser_runtime import browser_binaries, BrowserUnavailable

DOMAIN = 'myppc_local'
_LOGGER = logging.getLogger(__name__)


class Coordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(hass, _LOGGER, name='myPPC', update_interval=None)
        self.entry = entry
        self.directory = Path(hass.config.path('.storage', DOMAIN, entry.entry_id))
        self.runtime = Path(hass.config.path('.storage', DOMAIN, 'runtime'))
        self.lock = threading.Lock()

    def load_cache(self):
        """Restore saved readings without logging into PPC on every HA restart."""
        try:
            data = json.loads((self.directory / 'history.json').read_text())
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and data.get('updated_at') else None

    async def async_daily_refresh(self, now):
        """One fresh login and collection at 08:00 in HA's local timezone."""
        await self.async_refresh()

    def _blocking_update(self):
        with self.lock:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            gate = DailyGate(self.directory / 'schedule.json', self.entry.unique_id, self.hass.config.time_zone)
            cache = self.directory / 'history.json'
            previous = None
            try:
                previous = json.loads(cache.read_text())
            except (OSError, ValueError):
                pass
            # HA's local clock listener schedules collection at 08:00.
            # This file records diagnostics only; it does not schedule retries.
            browser_binaries()
            gate.reserve()
            try:
                api = Portal(self.runtime, self.entry.data['username'], self.entry.data['password'],
                             self.entry.data.get('payment_code',''))
                data = api.fetch(previous)
                temp = cache.with_suffix('.tmp')
                temp.write_text(json.dumps(data, ensure_ascii=False))
                temp.chmod(0o600)
                temp.replace(cache)
                gate.set_status('ok')
                return data
            except LoginRequired:
                gate.set_status('login_required')
                raise
            except Exception:
                gate.set_status('collection_failed')
                raise

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self._blocking_update)
        except LoginRequired as exc:
            # LoginRequired messages contain only our own fixed text or a
            # short, visible portal notice; credentials are never included.
            raise ConfigEntryAuthFailed(str(exc)) from exc
        except BrowserUnavailable as exc:
            raise UpdateFailed(str(exc)) from exc
        except UpdateFailed:
            raise
        except Exception as exc:
            _LOGGER.exception('myPPC collection failed: %s: %s', type(exc).__name__, exc)
            raise UpdateFailed(
                f'Citirea PPC a eșuat ({type(exc).__name__}: {exc}); '
                'nu s-a înlocuit soldul cu zero'
            ) from exc


async def async_setup_entry(hass, entry):
    coordinator = Coordinator(hass, entry)
    cached = await hass.async_add_executor_job(coordinator.load_cache)
    if cached is None:
        # First installation needs an initial reading to create the sensors.
        await coordinator.async_config_entry_first_refresh()
    else:
        coordinator.async_set_updated_data(cached)
    hass.data.setdefault(DOMAIN,{})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry,['sensor'])
    entry.async_on_unload(async_track_time_change(
        hass, coordinator.async_daily_refresh, hour=8, minute=0, second=0
    ))
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry,['sensor']):
        hass.data[DOMAIN].pop(entry.entry_id)
        return True
    return False

