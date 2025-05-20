"""Support for EZVIZ Cloud switches."""
import logging
import asyncio

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
        self._state_is_updating = False  # 状态更新锁
        self._command_queue = asyncio.Queue()  # 用于排队命令
        self._background_task = None  # 后台任务引用

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        # 确保设备在设备列表中且有信息
        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})
        device_info = device_data.get("info", {})

        # 检查设备状态
        return bool(device_info)

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

    def update_from_privacy_status(self, privacy_status):
        """直接从隐私状态更新实体状态。"""
        is_on = privacy_status == PRIVACY_ON
        if self._attr_is_on != is_on:
            self._attr_is_on = is_on
            self._attr_icon = "mdi:eye-off" if is_on else "mdi:eye"
            self.async_write_ha_state()
            _LOGGER.debug("直接更新实体状态 %s 到 %s", self.device_sn, privacy_status)

    async def async_update(self):
        """Update the switch state."""
        # 如果有命令正在处理，跳过常规更新
        if self._state_is_updating:
            return

        devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
        device_data = devices_data.get(self.device_sn, {})

        privacy_status = device_data.get("privacy_status", "unknown")
        is_on = privacy_status == PRIVACY_ON

        # 只有当状态变化时才更新
        if self._attr_is_on != is_on:
            self._attr_is_on = is_on
            self._attr_icon = "mdi:eye-off" if is_on else "mdi:eye"

    async def async_added_to_hass(self):
        """当实体被添加到Home Assistant时调用。"""
        # 启动后台任务处理开关命令
        self._background_task = self.hass.async_create_task(self._process_command_queue())

    async def async_will_remove_from_hass(self):
        """当实体将从Home Assistant移除时调用。"""
        # 清理后台任务
        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

    async def _process_command_queue(self):
        """处理后台命令队列。"""
        while True:
            try:
                # 从队列获取命令
                command, new_state = await self._command_queue.get()

                # 设置状态更新锁
                self._state_is_updating = True

                try:
                    # 执行命令
                    if command == "turn_on":
                        await self._do_turn_on()
                    elif command == "turn_off":
                        await self._do_turn_off()

                    # 验证状态变化
                    await self._verify_state_change(new_state)
                finally:
                    # 无论成功或失败，释放锁
                    self._state_is_updating = False
                    self._command_queue.task_done()
            except asyncio.CancelledError:
                # 任务被取消
                break
            except Exception as error:
                _LOGGER.exception("Error processing command: %s", error)
                self._state_is_updating = False
                self._command_queue.task_done()

    async def _verify_state_change(self, expected_state):
        """验证状态变更是否成功。"""
        MAX_RETRIES = 3
        RETRY_DELAY = 1  # 秒

        for attempt in range(MAX_RETRIES):
            try:
                # 主动获取当前状态而不是依赖缓存
                current_status = await self._client.get_privacy_status(self.device_sn)
                actual_state = PRIVACY_ON if current_status else PRIVACY_OFF

                if actual_state == expected_state:
                    # 状态已更新为预期值
                    _LOGGER.debug("状态验证成功: %s 在尝试 %s/%s", self.device_sn, attempt + 1, MAX_RETRIES)
                    # 更新数据存储
                    devices_data = self.hass.data[DOMAIN][self.entry_id]["devices"]
                    if self.device_sn in devices_data:
                        devices_data[self.device_sn]["privacy_status"] = expected_state
                    return True

                _LOGGER.debug(
                    "状态验证不匹配: %s 预期 %s, 实际 %s, 尝试 %s/%s",
                    self.device_sn, expected_state, actual_state, attempt + 1, MAX_RETRIES
                )

                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)
            except Exception as error:
                _LOGGER.error("验证状态时出错: %s", error)
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY)

        # 所有尝试都失败
        _LOGGER.warning("无法验证设备 %s 的状态更新", self.device_sn)
        return False

    async def async_turn_on(self, **kwargs):
        """Turn the privacy mode on."""
        # HomeKit需要立即返回以避免超时，所以我们立即更新状态
        self._attr_is_on = True
        self._attr_icon = "mdi:eye-off"
        self.async_write_ha_state()

        # 将实际命令放入队列异步处理
        await self._command_queue.put(("turn_on", PRIVACY_ON))

    async def _do_turn_on(self):
        """实际执行打开隐私模式的命令。"""
        _LOGGER.debug("执行打开隐私模式: %s", self.device_sn)
        try:
            success = await self._client.set_privacy(self.device_sn, True)
            if not success:
                _LOGGER.error("无法启用隐私模式: %s", self.device_sn)
                # 在验证阶段会处理状态还原
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("启用隐私模式时出错: %s", error)

    async def async_turn_off(self, **kwargs):
        """Turn the privacy mode off."""
        # HomeKit需要立即返回以避免超时，所以我们立即更新状态
        self._attr_is_on = False
        self._attr_icon = "mdi:eye"
        self.async_write_ha_state()

        # 将实际命令放入队列异步处理
        await self._command_queue.put(("turn_off", PRIVACY_OFF))

    async def _do_turn_off(self):
        """实际执行关闭隐私模式的命令。"""
        _LOGGER.debug("执行关闭隐私模式: %s", self.device_sn)
        try:
            success = await self._client.set_privacy(self.device_sn, False)
            if not success:
                _LOGGER.error("无法禁用隐私模式: %s", self.device_sn)
                # 在验证阶段会处理状态还原
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("禁用隐私模式时出错: %s", error)