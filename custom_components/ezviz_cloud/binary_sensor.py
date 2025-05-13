"""Support for EZVIZ binary sensors."""
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICES, PRIVACY_ON

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZVIZ binary sensors based on a config entry."""
    ezviz_data = hass.data[DOMAIN][entry.entry_id]
    client = ezviz_data["client"]
    devices = ezviz_data["devices"]

    # 获取配置的设备
    configured_devices = entry.data.get(CONF_DEVICES, [])

    sensors = []
    for device_sn in configured_devices:
        if device_sn in devices:
            sensors.append(EzvizPrivacySensor(hass, entry.entry_id, device_sn))

    async_add_entities(sensors, True)

class EzvizPrivacySensor(BinarySensorEntity):
    """Representation of a EZVIZ privacy sensor."""

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRIVACY

    def __init__(self, hass, entry_id, device_sn):
        """Initialize the EZVIZ privacy sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.device_sn = device_sn

        self._attr_name = "隐私状态"  # 使用中文名称
        self._attr_unique_id = f"{device_sn}_privacy_status"
        self._attr_is_on = False

    @property
    def device_info(self):
        """Return device information about this EZVIZ sensor."""
        device_info = self.hass.data[DOMAIN][self.entry_id]["devices"].get(self.device_sn, {}).get("info", {})
        # 根据中国API调整字段名
        device_name = device_info.get("deviceName", self.device_sn)
        device_type = device_info.get("deviceType", "Camera")
        sw_version = device_info.get("version", "Unknown")

        return {
            "identifiers": {(DOMAIN, self.device_sn)},
            "name": device_name,
            "manufacturer": "萤石",  # 使用中文名称
            "model": device_type,
            "sw_version": sw_version,
        }

    async def async_update(self):
        """Update the sensor state."""
        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})

        privacy_status = device_data.get("privacy_status", "unknown")
        self._attr_is_on = privacy_status == PRIVACY_ON