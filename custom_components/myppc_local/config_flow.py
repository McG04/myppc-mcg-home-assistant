"""Store credentials locally in the native Home Assistant configuration entry."""
import hashlib
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from . import DOMAIN


class ConfigFlow(config_entries.ConfigFlow,domain=DOMAIN):
    VERSION=1

    async def async_step_user(self,user_input=None):
        errors={}
        if user_input is not None:
            if not user_input['username'].strip() or not user_input['password']:
                errors['base']='invalid_auth'
            else:
                data={**user_input,'username':user_input['username'].strip(),
                      'payment_code':user_input.get('payment_code','').strip()}
                if data['payment_code'] and not data['payment_code'].isdigit():
                    errors['base']='invalid_code'
                elif self.context.get('source')=='reauth':
                    entry=self._get_reauth_entry()
                    return self.async_update_reload_and_abort(entry,data_updates=data)
                else:
                    unique=hashlib.sha256((data['username'].lower()+':'+data['payment_code']).encode()).hexdigest()
                    await self.async_set_unique_id(unique)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title='myPPC',data=data)
        return self.async_show_form(step_id='user',errors=errors,data_schema=vol.Schema({
            vol.Required('username'):str,
            vol.Required('password'):selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional('payment_code',default=''):str,
        }))

    async def async_step_reauth(self,entry_data):
        return await self.async_step_user()
