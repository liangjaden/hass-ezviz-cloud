"""Support for EZVIZ binary sensors."""
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

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
    if not configured_devices:
        _LOGGER.info("No devices configured for binary sensors, skipping setup")
        return

    sensors = []
    for device_sn in configured_devices:
        if device_sn in devices:
            sensors.append(EzvizPrivacySensor(hass, entry.entry_id, device_sn))

    async_add_entities(sensors, True)

    # 注册回调函数，用于监听隐私状态变化
    hass.bus.async_listen(f"{DOMAIN}_privacy_changed", _handle_privacy_event)

    @callback
    def _handle_privacy_event(event):
        """处理隐私状态变化事件。"""
        device_sn = event.data.get("device_sn")
        new_status = event.data.get("new_status")

        # 查找对应的传感器并更新状态
        for sensor in sensors:
            if sensor.device_sn == device_sn:
                sensor.update_from_event(new_status)
                break

class EzvizPrivacySensor(BinarySensorEntity):
    """Representation of a EZVIZ privacy sensor."""

    _attr_has_entity_name = True
    # 使用兼容的设备类
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY  # 或者其他合适的设备类

    def __init__(self, hass, entry_id, device_sn):
        """Initialize the EZVIZ privacy sensor."""
        self.hass = hass
        self.entry_id = entry_id
        self.device_sn = device_sn

        self._attr_name = "隐私状态"  # 使用中文名称
        self._attr_unique_id = f"{device_sn}_privacy_status"
        self._attr_is_on = False

        # 添加额外的属性用于HomeKit
        self._attr_available = True
        self._attr_should_poll = False  # 不需要轮询，依靠事件更新

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this EZVIZ sensor."""
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

    @callback
    def update_from_event(self, privacy_status):
        """从事件更新实体状态。"""
        is_on = privacy_status == PRIVACY_ON
        if self._attr_is_on != is_on:
            _LOGGER.debug("更新传感器 %s 状态到 %s", self.entity_id, is_on)
            self._attr_is_on = is_on
            self.async_write_ha_state()

    async def async_update(self):
        """Update the sensor state."""
        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})

        privacy_status = device_data.get("privacy_status", "unknown")
        self._attr_is_on = privacy_status == PRIVACY_ON

        # 确保实体可用
        if not self._attr_available:
            self._attr_available = True
            _LOGGER.debug("传感器 %s 现在可用", self.entity_id)