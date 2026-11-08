"""Regression tests without downloading HA or launching a real browser."""
import ast
import asyncio
from datetime import datetime, timedelta
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1] / 'custom_components/myppc_local'


def load_source(name, dependencies):
    tree = ast.parse((ROOT / name).read_text())
    tree.body = [node for node in tree.body if not (
        isinstance(node, ast.ImportFrom) and
        (node.level or node.module.startswith(('homeassistant', 'selenium')))
    )]
    scope = dict(dependencies)
    exec(compile(tree, str(ROOT / name), 'exec'), scope)
    return scope


class DailyTests(unittest.TestCase):
    def test_next_check_follows_local_clock_across_dst(self):
        gate_class = load_source('daily.py', {})['DailyGate']
        with tempfile.TemporaryDirectory() as directory:
            for start, hours in [('2026-03-28T08:00:00', 23),
                                 ('2026-10-24T08:00:00', 25),
                                 ('2026-11-01T08:00:00', 24)]:
                now = datetime.fromisoformat(start).replace(tzinfo=ZoneInfo('Europe/Bucharest'))
                gate = gate_class(Path(directory) / 'schedule.json', 'test')
                gate.reserve(now.timestamp())
                next_time = datetime.fromtimestamp(gate.next_check, now.tzinfo)
                self.assertEqual(next_time.hour, 8)
                self.assertEqual(gate.next_check - now.timestamp(), hours * 3600)


class TimeoutException(Exception):
    pass


class LoginTests(unittest.TestCase):
    def portal_scope(self, notice):
        driver = MagicMock()
        driver.current_url = 'https://myppc.ppcenergy.ro/autentificare'
        username, password, button = MagicMock(), MagicMock(), MagicMock()
        username.get_attribute.return_value = 'email'
        password.get_attribute.return_value = 'password'
        username.is_displayed.return_value = password.is_displayed.return_value = True
        button.is_displayed.return_value = True
        alert = MagicMock()
        alert.text = notice
        alert.is_displayed.return_value = True
        def elements(by, selector):
            if selector == 'input':
                return [username, password]
            if selector == 'button[type="submit"]':
                return [button]
            if selector == '[role="alert"]' and notice:
                return [alert]
            return []
        driver.find_elements.side_effect = elements
        webdriver = MagicMock()
        webdriver.Chrome.return_value = driver
        wait = MagicMock()
        wait.until.side_effect = [True, TimeoutException()]
        scope = load_source('portal.py', dict(
            webdriver=webdriver, Service=MagicMock(),
            By=types.SimpleNamespace(TAG_NAME='tag', CSS_SELECTOR='css'),
            WebDriverWait=MagicMock(return_value=wait), TimeoutException=TimeoutException,
            browser_binaries=lambda runtime: ('chrome', 'driver', None),
            merge_records=MagicMock(), rows=MagicMock(), normalize=MagicMock()))
        return scope, driver

    def test_timeout_does_not_request_new_credentials(self):
        scope, driver = self.portal_scope('')
        with tempfile.TemporaryDirectory() as directory:
            portal = scope['Portal'](directory, 'test', 'secret')
            with self.assertRaises(scope['PortalError']):
                portal.login()
        driver.quit.assert_called_once()

    def test_explicit_password_rejection_requests_reauth(self):
        scope, driver = self.portal_scope('Parolă incorectă')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(scope['LoginRequired']):
                scope['Portal'](directory, 'test', 'secret').login()
        driver.quit.assert_called_once()


class FakeCoordinator:
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.update_interval = kwargs['update_interval']
        self.first_refreshes = 0
    async def async_config_entry_first_refresh(self):
        self.first_refreshes += 1
    async def async_refresh(self):
        pass

    def async_set_updated_data(self, data):
        self.data = data


class SetupTests(unittest.IsolatedAsyncioTestCase):
    async def test_restart_with_current_cache_schedules_only_eight(self):
        await self.check_restart(stale=False)

    async def test_restart_catches_up_a_missed_reading(self):
        await self.check_restart(stale=True)

    async def test_restart_does_not_repeat_todays_failed_attempt(self):
        await self.check_restart(stale=True, attempted=True)

    async def check_restart(self, *, stale, attempted=False):
        tracker = MagicMock(return_value=lambda: None)
        scope = load_source('__init__.py', dict(
            ConfigEntryAuthFailed=type('AuthError', (Exception,), {}),
            async_track_time_change=tracker, DataUpdateCoordinator=FakeCoordinator,
            UpdateFailed=type('UpdateFailed', (Exception,), {}),
            DailyGate=load_source('daily.py', {})['DailyGate'],
            Portal=MagicMock(), LoginRequired=type('LoginRequired', (Exception,), {}),
            browser_binaries=MagicMock(), BrowserUnavailable=type('BrowserUnavailable', (Exception,), {})))
        with tempfile.TemporaryDirectory() as directory:
            async def executor(fn, *args):
                return fn(*args)
            async def forward(*args):
                pass
            hass = types.SimpleNamespace(data={},
                config=types.SimpleNamespace(time_zone='Europe/Bucharest',
                    path=lambda *parts: str(Path(directory).joinpath(*parts))),
                async_add_executor_job=executor,
                config_entries=types.SimpleNamespace(async_forward_entry_setups=forward))
            def track_background(hass, coro, name):
                coro.close()

            entry = types.SimpleNamespace(entry_id='test', unique_id='test',
                async_on_unload=MagicMock(), async_create_background_task=MagicMock(
                    side_effect=track_background))
            path = Path(directory) / '.storage/myppc_local/test/history.json'
            path.parent.mkdir(parents=True)
            now = datetime.now(ZoneInfo('Europe/Bucharest'))
            updated = now - timedelta(days=7) if stale else now
            saved = {'updated_at': updated.isoformat(), 'balance': 12}
            if attempted:
                scope['DailyGate'](path.with_name('schedule.json'), 'test').reserve(now.timestamp())
            path.write_text(json.dumps(saved))
            await scope['async_setup_entry'](hass, entry)
            coordinator = hass.data['myppc_local']['test']
            self.assertEqual(coordinator.data, saved)
            self.assertEqual(coordinator.first_refreshes, 0)
            self.assertIsNone(coordinator.update_interval)
            self.assertEqual(tracker.call_args.kwargs, {'hour': 8, 'minute': 0, 'second': 0})
            entry.async_on_unload.assert_called_once()
            scope['Portal'].assert_not_called()
            if stale and not attempted:
                entry.async_create_background_task.assert_called_once()
            else:
                entry.async_create_background_task.assert_not_called()


if __name__ == '__main__':
    unittest.main()

