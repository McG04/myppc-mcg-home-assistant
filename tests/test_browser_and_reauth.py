"""Regression tests for preinstalled browsers and validated reauthentication."""
import asyncio
import hashlib
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

from test_daily_login import load_source


class BrowserTests(unittest.TestCase):
    def test_existing_pair_is_returned_without_creating_runtime_files(self):
        scope = load_source('browser_runtime.py', {})
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(scope['shutil'], 'which', side_effect=lambda name: {
                'chromium': '/usr/bin/chromium', 'chromedriver': '/usr/bin/chromedriver'
            }.get(name)):
                self.assertEqual(scope['browser_binaries'](), ('/usr/bin/chromium', '/usr/bin/chromedriver', None))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_missing_pair_fails_without_a_preprovisioned_runtime(self):
        scope = load_source('browser_runtime.py', {})
        for available in ({}, {'chromium': '/usr/bin/chromium'}, {'chromedriver': '/usr/bin/chromedriver'}):
            with self.subTest(available=available), patch.object(scope['shutil'], 'which', side_effect=available.get):
                with self.assertRaises(scope['BrowserUnavailable']):
                    scope['browser_binaries']()

    def test_existing_alpine_pair_is_used_without_running_wrappers(self):
        scope = load_source('browser_runtime.py', {})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / 'alpine-browser'
            expected = [root / 'usr/lib/chromium/chromium', root / 'usr/bin/chromedriver']
            for path in expected:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch(mode=0o700)
            with patch.object(scope['shutil'], 'which', return_value=None):
                chrome, driver, env = scope['browser_binaries'](directory)
                self.assertEqual([Path(chrome), Path(driver)], expected)
                self.assertIn(str(root / 'usr/lib'), env['LD_LIBRARY_PATH'])
                expected[1].chmod(0o600)
                with self.assertRaises(scope['BrowserUnavailable']):
                    scope['browser_binaries'](directory)

    def test_chromium_browser_name_is_supported(self):
        scope = load_source('browser_runtime.py', {})
        with patch.object(scope['shutil'], 'which', side_effect=lambda name: {
            'chromium-browser': '/usr/bin/chromium-browser', 'chromedriver': '/usr/bin/chromedriver'
        }.get(name)):
            self.assertEqual(scope['browser_binaries']()[0], '/usr/bin/chromium-browser')


class FlowBase:
    def __init_subclass__(cls, **kwargs):
        pass

    def _get_reauth_entry(self):
        return self.entry

    def async_show_form(self, **kwargs):
        return {'type': 'form', **kwargs}

    def async_update_reload_and_abort(self, entry, *, data_updates):
        self.reloaded = entry
        entry.data = {**entry.data, **data_updates}
        return {'type': 'abort', 'reason': 'reauth_successful'}


class LoginRequired(Exception):
    pass


class PortalError(Exception):
    pass


class BrowserUnavailable(Exception):
    pass


class WebDriverException(Exception):
    pass


class ReauthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        fake_vol = types.ModuleType('voluptuous')
        fake_vol.Schema = lambda value: value
        fake_vol.Required = lambda name, **kwargs: name
        fake_vol.Optional = lambda name, **kwargs: name
        with patch.dict(sys.modules, voluptuous=fake_vol):
            self.scope = load_source('config_flow.py', {
                'config_entries': types.SimpleNamespace(ConfigFlow=FlowBase),
                'selector': types.SimpleNamespace(TextSelector=lambda c: c,
                    TextSelectorConfig=lambda **kw: kw, TextSelectorType=types.SimpleNamespace(PASSWORD='password')),
                'DOMAIN': 'myppc_local', 'LoginRequired': LoginRequired,
                'PortalError': PortalError, 'BrowserUnavailable': BrowserUnavailable,
                'WebDriverException': WebDriverException, 'Portal': MagicMock(),
            })
        self.failure = None
        self.calls = []

        async def executor(fn, *args):
            self.calls.append(args)
            if self.failure:
                raise self.failure
            return fn(*args)

        self.flow = self.scope['ConfigFlow']()
        self.flow.hass = types.SimpleNamespace(async_add_executor_job=executor,
            config=types.SimpleNamespace(path=lambda *parts: str(Path('/config').joinpath(*parts))))
        self.flow.entry = types.SimpleNamespace(entry_id='existing', unique_id='unchanged',
            data={'username': 'user@example.test', 'password': 'old', 'payment_code': '123'},
            options={'custom': True})
        self.flow.reloaded = None

    async def submit(self, username='user@example.test', password='new'):
        return await self.flow.async_step_reauth_confirm({'username': username, 'password': password})

    async def test_initial_reauth_only_displays_form(self):
        result = await self.flow.async_step_reauth(self.flow.entry.data)
        self.assertEqual(result['step_id'], 'reauth_confirm')
        self.assertFalse(self.calls)
        self.scope['Portal'].assert_not_called()

    async def test_success_validates_login_then_updates_the_existing_entry(self):
        result = await self.submit(' USER@EXAMPLE.TEST ')
        self.assertEqual(result['reason'], 'reauth_successful')
        self.assertEqual(self.calls, [('USER@EXAMPLE.TEST', 'new', '/config/.storage/myppc_local/runtime')])
        self.scope['Portal'].return_value.login.assert_called_once_with()
        self.scope['Portal'].return_value.fetch.assert_not_called()
        self.assertIs(self.flow.reloaded, self.flow.entry)
        self.assertEqual(self.flow.entry.data['payment_code'], '123')
        self.assertEqual(self.flow.entry.data['password'], 'new')
        self.assertEqual(self.flow.entry.unique_id, 'unchanged')
        self.assertEqual(self.flow.entry.options, {'custom': True})
        profile = Path(self.scope['Portal'].call_args.args[0])
        self.assertFalse(profile.exists())

    async def test_rejected_login_does_not_save_credentials_or_reload(self):
        self.scope['Portal'].return_value.login.side_effect = LoginRequired()
        result = await self.submit()
        self.assertEqual(result['errors'], {'base': 'invalid_auth'})
        self.assertEqual(self.flow.entry.data['password'], 'old')
        self.assertIsNone(self.flow.reloaded)
        self.assertFalse(Path(self.scope['Portal'].call_args.args[0]).exists())

    async def test_temporary_failure_and_missing_browser_do_not_save(self):
        for failure, code in [(PortalError(), 'cannot_connect'),
                              (WebDriverException(), 'cannot_connect'),
                              (OSError(), 'cannot_connect'),
                              (BrowserUnavailable(), 'browser_unavailable')]:
            self.failure = failure
            result = await self.submit()
            self.assertEqual(result['errors'], {'base': code})
            self.assertEqual(self.flow.entry.data['password'], 'old')
            self.assertIsNone(self.flow.reloaded)

    async def test_empty_or_other_account_is_rejected_before_login(self):
        for username, password, code in [('user@example.test', '', 'invalid_auth'),
                                         ('', 'new', 'invalid_auth'),
                                         ('other@example.test', 'new', 'wrong_account')]:
            result = await self.submit(username, password)
            self.assertEqual(result['errors'], {'base': code})
            self.assertFalse(self.calls)
        self.assertEqual(self.flow.entry.data['password'], 'old')


if __name__ == '__main__':
    unittest.main()
