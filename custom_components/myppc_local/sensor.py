from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.entity import DeviceInfo
from . import DOMAIN

FIELDS = {
    'balance': ('Sold net', 'mdi:scale-balance'),
    'amount_due': ('De plată', 'mdi:cash-clock'),
    'credit': ('Avans disponibil', 'mdi:cash-plus'),
    'latest_invoice': ('Ultima factură', 'mdi:receipt-text'),
    'latest_payment': ('Ultima plată', 'mdi:cash-check'),
    'invoice_history': ('Istoric facturi', 'mdi:receipt-text-outline'),
    'payment_history': ('Istoric plăți', 'mdi:cash-multiple'),
    'updated_at': ('Ultima citire', 'mdi:update'),
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PPCSensor(hass.data[DOMAIN][entry.entry_id], entry, key) for key in FIELDS])


class PPCSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_name, self._attr_icon = FIELDS[key]
        self._attr_unique_id = f'{entry.unique_id}_{key}'
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.unique_id)},
                                           name='myPPC', manufacturer='PPC', model='Portal myPPC')
        if key == 'updated_at':
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
            self._attr_native_unit_of_measurement = None
        elif key in ('invoice_history', 'payment_history'):
            self._attr_device_class = None
            self._attr_native_unit_of_measurement = 'înregistrări'
        else:
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = 'RON'

    @property
    def native_value(self):
        from datetime import datetime
        from decimal import Decimal
        data = self.coordinator.data
        if self.key == 'updated_at':
            return datetime.fromisoformat(data[self.key])
        if self.key == 'invoice_history':
            return len(data['invoices'])
        if self.key == 'payment_history':
            return len(data['payments'])
        value = data[self.key]
        if value is None:
            return None
        return Decimal(value['amount'] if isinstance(value, dict) else value)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        if self.key == 'latest_invoice':
            return {**(data['latest_invoice'] or {}), **data['latest_invoice_detail'],
                    'history': data['invoices'], 'history_complete': data['history_complete']}
        if self.key == 'latest_payment':
            clean = lambda row: {k:v for k,v in row.items() if k != 'id'}
            return {**clean(data['latest_payment'] or {}), 'history': [clean(r) for r in data['payments']],
                    'history_complete': False}
        if self.key == 'invoice_history':
            return {'history': data['invoices'], 'history_complete': data['history_complete'],
                    'scope': data['history_scope'], 'myppc_history_type': 'invoices'}
        if self.key == 'payment_history':
            clean = lambda row: {k:v for k,v in row.items() if k != 'id'}
            return {'history': [clean(r) for r in data['payments']],
                    'history_complete': False, 'scope': data['history_scope'],
                    'myppc_history_type': 'payments'}
        if self.key == 'balance':
            return {'source': data['balance_source'], 'updated_at': data['updated_at'],
                    'sign': 'pozitiv = datorie; negativ = avans'}
        return {}
