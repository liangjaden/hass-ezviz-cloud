"""Support for EZVIZ Cloud switches."""
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICES, PRIVACY_ON, PRIVACY_OFF
from .api import EzvizCloudChinaApiError

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
    if not configured_devices:
        _LOGGER.info("No devices configured for switches, skipping setup")
        return

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
        self._attr_name = "隐私模式"  # 使用中文名称
        self._attr_unique_id = f"{device_sn}_privacy_mode"
        self._attr_is_on = False
        self._attr_icon = "mdi:eye-off" if self._attr_is_on else "mdi:eye"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this EZVIZ device."""
        device_info = self.hass.data[DOMAIN][self.entry_id]["devices"].get(self.device_sn, {}).get("info", {})
        # 根据中国API调整字段名
        device_name = device_info.get("deviceName", self.device_sn)
        device_type = device_info.get("deviceType", "Camera")
        sw_version = device_info.get("version", "Unknown")

        return DeviceInfo(
            identifiers={(DOMAIN, self.device_sn)},
            name=device_name,
            manufacturer="萤石",
            model=device_type,
            sw_version=sw_version,
        )

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
            # 使用中国API开启隐私模式
            success = await self._client.set_privacy(self.device_sn, True)
            if success:
                self._attr_is_on = True
                self._attr_icon = "mdi:eye-off"
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to enable privacy mode for %s", self.device_sn)
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("Failed to enable privacy mode: %s", error)

    async def async_turn_off(self, **kwargs):
        """Turn the privacy mode off."""
        try:
            # 使用中国API关闭隐私模式
            success = await self._client.set_privacy(self.device_sn, False)
            if success:
                self._attr_is_on = False
                self._attr_icon = "mdi:eye"
                self.async_write_ha_state()
            else:
                _LOGGER.error("Failed to disable privacy mode for %s", self.device_sn)
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("Failed to disable privacy mode: %s", error)