"""Configure myPPC and validate replacement credentials against the portal."""
import hashlib
import tempfile

import voluptuous as vol
from selenium.common.exceptions import WebDriverException

from homeassistant import config_entries
from homeassistant.helpers import selector

from . import DOMAIN
from .browser_runtime import BrowserUnavailable
from .portal import LoginRequired, Portal, PortalError


def _validate_credentials(username, password, runtime):
    """Perform a real login in an isolated profile, without fetching billing data."""
    with tempfile.TemporaryDirectory(prefix="myppc-reauth-") as directory:
        Portal(directory, username, password, runtime=runtime).login()


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            if not user_input['username'].strip() or not user_input['password']:
                errors['base'] = 'invalid_auth'
            else:
                data = {**user_input, 'username': user_input['username'].strip(),
                        'payment_code': user_input.get('payment_code', '').strip()}
                if data['payment_code'] and not data['payment_code'].isdigit():
                    errors['base'] = 'invalid_code'
                else:
                    unique = hashlib.sha256((data['username'].lower() + ':' + data['payment_code']).encode()).hexdigest()
                    await self.async_set_unique_id(unique)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title='myPPC', data=data)
        return self.async_show_form(step_id='user', errors=errors, data_schema=vol.Schema({
            vol.Required('username'): str,
            vol.Required('password'): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional('payment_code', default=''): str,
        }))

    async def async_step_reauth(self, entry_data):
        """Request replacement credentials for the existing account."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Only save credentials after the portal confirms a successful login."""
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            username = user_input['username'].strip()
            password = user_input['password']
            if not username or not password:
                errors['base'] = 'invalid_auth'
            elif username.lower() != entry.data['username'].lower():
                errors['base'] = 'wrong_account'
            else:
                try:
                    await self.hass.async_add_executor_job(
                        _validate_credentials, username, password,
                        self.hass.config.path(".storage", DOMAIN, "runtime"),
                    )
                except LoginRequired:
                    errors['base'] = 'invalid_auth'
                except BrowserUnavailable:
                    errors['base'] = 'browser_unavailable'
                except (PortalError, WebDriverException, OSError):
                    errors['base'] = 'cannot_connect'
                else:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={'username': username, 'password': password}
                    )
        return self.async_show_form(
            step_id='reauth_confirm', errors=errors,
            data_schema=vol.Schema({
                vol.Required('username', default=entry.data['username']): str,
                vol.Required('password'): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }),
        )
