"""Support for EZVIZ Cloud switches with HomeKit Bridge compatibility."""
import logging
import asyncio
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import HomeAssistantError

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

    # 注册回调函数，当设备状态更新时
    async def handle_device_update(device_sn, privacy_status):
        """Handle device privacy status update."""
        for entity in switches:
            if entity.device_sn == device_sn:
                # 直接更新状态而不是等待下一次轮询
                entity.update_from_privacy_status(privacy_status)
                break

    # 保存回调函数以供__init__.py使用
    ezviz_data["device_callbacks"] = handle_device_update


class EzvizPrivacySwitch(SwitchEntity):
    """Representation of an EZVIZ privacy switch with HomeKit Bridge compatibility."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_should_poll = False  # 禁用轮询，依赖事件更新

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

        # HomeKit 兼容性增强
        self._attr_available = True
        self._is_turning_on = False
        self._is_turning_off = False
        self._last_command_time = 0

        # 命令处理队列
        self._command_lock = asyncio.Lock()
        self._pending_state = None  # 等待确认的状态

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # 确保设备在设备列表中且有信息
        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})
        device_info = device_data.get("info", {})

        # 检查设备状态
        return bool(device_info) and self._attr_available

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

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for HomeKit compatibility."""
        return {
            "device_sn": self.device_sn,
            "last_update": self._last_command_time,
            "is_privacy_mode": self._attr_is_on,
        }

    @callback
    def update_from_privacy_status(self, privacy_status):
        """直接从隐私状态更新实体状态，确保HomeKit同步。"""
        is_on = privacy_status == PRIVACY_ON

        # 如果状态已经匹配，并且没有等待中的状态，跳过更新
        if self._attr_is_on == is_on and self._pending_state is None:
            return

        # 更新状态
        if self._attr_is_on != is_on:
            self._attr_is_on = is_on
            self._attr_icon = "mdi:eye-off" if is_on else "mdi:eye"

            # 清除等待状态（如果匹配）
            if self._pending_state == privacy_status:
                self._pending_state = None
                self._is_turning_on = False
                self._is_turning_off = False

            # 立即写入状态以确保HomeKit获得响应
            self.async_write_ha_state()
            _LOGGER.debug("Updated switch %s state to %s", self.device_sn, privacy_status)

    async def async_update(self):
        """Update the switch state from stored data."""
        # 只有在没有等待命令时才从存储数据更新
        if self._is_turning_on or self._is_turning_off:
            return

        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})

        privacy_status = device_data.get("privacy_status", "unknown")
        is_on = privacy_status == PRIVACY_ON

        # 只有当状态变化时才更新
        if self._attr_is_on != is_on:
            self._attr_is_on = is_on
            self._attr_icon = "mdi:eye-off" if is_on else "mdi:eye"

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the privacy mode on with HomeKit optimized response."""
        if self._is_turning_on:
            return  # 防止重复命令

        async with self._command_lock:
            try:
                self._is_turning_on = True
                self._pending_state = PRIVACY_ON

                # 立即更新UI状态以提供快速反馈给HomeKit
                self._attr_is_on = True
                self._attr_icon = "mdi:eye-off"
                self.async_write_ha_state()

                # 执行实际的API调用
                success = await self._execute_privacy_command(True)

                if not success:
                    # 如果命令失败，恢复原状态
                    _LOGGER.error("Failed to enable privacy mode for device %s", self.device_sn)
                    await self._revert_state()
                    raise HomeAssistantError(f"Failed to enable privacy mode for device {self.device_sn}")
                else:
                    # 成功后记录时间
                    import time
                    self._last_command_time = time.time()

            except Exception as error:
                await self._revert_state()
                _LOGGER.error("Error turning on privacy mode: %s", error)
                raise HomeAssistantError(f"Error turning on privacy mode: {error}")
            finally:
                self._is_turning_on = False

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the privacy mode off with HomeKit optimized response."""
        if self._is_turning_off:
            return  # 防止重复命令

        async with self._command_lock:
            try:
                self._is_turning_off = True
                self._pending_state = PRIVACY_OFF

                # 立即更新UI状态以提供快速反馈给HomeKit
                self._attr_is_on = False
                self._attr_icon = "mdi:eye"
                self.async_write_ha_state()

                # 执行实际的API调用
                success = await self._execute_privacy_command(False)

                if not success:
                    # 如果命令失败，恢复原状态
                    _LOGGER.error("Failed to disable privacy mode for device %s", self.device_sn)
                    await self._revert_state()
                    raise HomeAssistantError(f"Failed to disable privacy mode for device {self.device_sn}")
                else:
                    # 成功后记录时间
                    import time
                    self._last_command_time = time.time()

            except Exception as error:
                await self._revert_state()
                _LOGGER.error("Error turning off privacy mode: %s", error)
                raise HomeAssistantError(f"Error turning off privacy mode: {error}")
            finally:
                self._is_turning_off = False

    async def _execute_privacy_command(self, enable: bool, max_retries: int = 2) -> bool:
        """Execute the privacy command with retries and verification."""
        for attempt in range(max_retries + 1):
            try:
                # 执行API命令
                success = await self._client.set_privacy(self.device_sn, enable)

                if success:
                    # 短暂延迟后验证状态
                    await asyncio.sleep(0.5)

                    # 验证状态是否正确设置
                    try:
                        current_status = await self._client.get_privacy_status(self.device_sn)
                        expected_status = enable

                        if current_status == expected_status:
                            _LOGGER.debug("Privacy command successful for %s: %s", self.device_sn, enable)
                            return True
                        else:
                            _LOGGER.warning("Privacy command status mismatch for %s: expected %s, got %s",
                                            self.device_sn, expected_status, current_status)
                    except Exception as verify_error:
                        _LOGGER.warning("Failed to verify privacy status for %s: %s", self.device_sn, verify_error)
                        # 如果验证失败但命令成功，仍然认为操作成功
                        return True

                # 如果不是最后一次尝试，等待后重试
                if attempt < max_retries:
                    wait_time = (attempt + 1) * 1.0  # 递增等待时间
                    _LOGGER.warning("Privacy command failed for %s (attempt %d/%d), retrying in %.1fs",
                                    self.device_sn, attempt + 1, max_retries + 1, wait_time)
                    await asyncio.sleep(wait_time)

            except EzvizCloudChinaApiError as api_error:
                if attempt < max_retries:
                    wait_time = (attempt + 1) * 1.0
                    _LOGGER.warning("API error for %s (attempt %d/%d): %s, retrying in %.1fs",
                                    self.device_sn, attempt + 1, max_retries + 1, api_error, wait_time)
                    await asyncio.sleep(wait_time)
                else:
                    _LOGGER.error("API error for %s after %d attempts: %s", self.device_sn, max_retries + 1, api_error)
                    return False
            except Exception as error:
                _LOGGER.error("Unexpected error executing privacy command for %s: %s", self.device_sn, error)
                return False

        _LOGGER.error("Privacy command failed for %s after %d attempts", self.device_sn, max_retries + 1)
        return False

    async def _revert_state(self):
        """Revert the entity state to match the actual device state."""
        try:
            # 获取当前实际状态
            devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
            device_data = devices_data.get(self.device_sn, {})
            actual_privacy_status = device_data.get("privacy_status", PRIVACY_OFF)

            # 恢复到实际状态
            actual_is_on = actual_privacy_status == PRIVACY_ON
            self._attr_is_on = actual_is_on
            self._attr_icon = "mdi:eye-off" if actual_is_on else "mdi:eye"
            self._pending_state = None

            # 写入恢复的状态
            self.async_write_ha_state()
            _LOGGER.debug("Reverted state for %s to actual state: %s", self.device_sn, actual_privacy_status)

        except Exception as error:
            _LOGGER.error("Error reverting state for %s: %s", self.device_sn, error)

    async def async_added_to_hass(self) -> None:
        """Called when entity is added to Home Assistant."""
        # 确保实体在添加时是可用的
        self._attr_available = True

        # 获取初始状态
        await self.async_update()

        _LOGGER.debug("EZVIZ privacy switch %s added to Home Assistant", self.device_sn)

    async def async_will_remove_from_hass(self) -> None:
        """Called when entity will be removed from Home Assistant."""
        # 清理任何待处理的操作
        self._pending_state = None
        self._is_turning_on = False
        self._is_turning_off = False

        _LOGGER.debug("EZVIZ privacy switch %s will be removed from Home Assistant", self.device_sn)