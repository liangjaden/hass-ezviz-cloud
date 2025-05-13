"""Support for EZVIZ Cloud switches."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICES, PRIVACY_ON, PRIVACY_OFF

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZVIZ switches based on a config entry."""
    ezviz_data = hass.data[DOMAIN][entry.entry_id]
    client = ezviz_data["client"]
    devices = ezviz_data["devices"]

    # 获取配置的设备
    configured_devices = entry.data.get(CONF_DEVICES, [])

    switches = []
    for device_sn in configured_devices:
        if device_sn in devices:
            switches.append(EzvizPrivacySwitch(hass, entry.entry_id, device_sn))

    async_add_entities(switches, True)

class EzvizPrivacySwitch(SwitchEntity):
    """Representation of an EZVIZ privacy switch."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass, entry_id, device_sn):
        """Initialize the EZVIZ privacy switch."""
        self.hass = hass
        self.entry_id = entry_id
        self.device_sn = device_sn

        self._client = hass.data[DOMAIN][entry_id]["client"]
        self._attr_name = f"Privacy Mode"
        self._attr_unique_id = f"{device_sn}_privacy_mode"
        self._attr_is_on = False
        self._attr_icon = "mdi:eye-off" if self._attr_is_on else "mdi:eye"

    @property
    def device_info(self):
        """Return device information about this EZVIZ device."""
        device_info = self.hass.data[DOMAIN][self.entry_id]["devices"].get(self.device_sn, {}).get("info", {})
        device_name = device_info.get("device_name", self.device_sn)

        return {
            "identifiers": {(DOMAIN, self.device_sn)},
            "name": device_name,
            "manufacturer": "EZVIZ",
            "model": device_info.get("device_type", "Camera"),
            "sw_version": device_info.get("version", "Unknown"),
        }

    async def async_update(self):
        """Update the switch state."""
        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})

        privacy_status = device_data.get("privacy_status", "unknown")
        self._attr_is_on = privacy_status == PRIVACY_ON
        self._attr_icon = "mdi:eye-off" if self._attr_is_on else "mdi:eye"

    async def async_turn_on(self, **kwargs):
        """Turn the privacy mode on."""
        try:
            await self.hass.async_add_executor_job(
                self._client.enable_privacy_mode, self.device_sn
            )
            self._attr_is_on = True
            self._attr_icon = "mdi:eye-off"
            self.async_write_ha_state()
        except Exception as error:
            _LOGGER.error("Failed to enable privacy mode: %s", error)

    async def async_turn_off(self, **kwargs):
        """Turn the privacy mode off."""
        try:
            await self.hass.async_add_executor_job(
                self._client.disable_privacy_mode, self.device_sn
            )
            self._attr_is_on = False
            self._attr_icon = "mdi:eye"
            self.async_write_ha_state()
        except Exception as error:
            _LOGGER.error("Failed to disable privacy mode: %s", error)