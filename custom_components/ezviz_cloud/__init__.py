"""The EZVIZ Cloud integration for Chinese market with HomeKit Bridge compatibility."""
import asyncio
import logging
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.const import Platform

from .api import EzvizCloudChinaApi, EzvizCloudChinaApiError
from .const import (
    DOMAIN,
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_DEVICES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    EVENT_PRIVACY_CHANGED,
    CONF_WEBHOOK_URL,
    PRIVACY_ON,
    PRIVACY_OFF,
    HOMEKIT_SUPPORT_ENABLED,
)

_LOGGER = logging.getLogger(__name__)

# 使用Platform枚举进行平台定义
PLATFORMS = [Platform.CAMERA, Platform.SWITCH, Platform.BINARY_SENSOR]

# 翻译文件内容
EN_TRANSLATIONS = {
    "config": {
        "step": {
            "user": {
                "title": "EZVIZ Cloud (China)",
                "description": "Set up EZVIZ Cloud integration for the Chinese market",
                "data": {
                    "app_key": "App Key",
                    "app_secret": "App Secret"
                }
            },
            "webhook": {
                "title": "WeCom Webhook Notification",
                "description": "Configure a WeCom webhook URL to receive notifications when privacy status changes",
                "data": {
                    "webhook_url": "WeCom Webhook URL (Optional)"
                }
            },
            "devices": {
                "title": "Select Devices",
                "description": "Select the devices you want to monitor. You can leave this empty and configure it later.",
                "data": {
                    "devices": "Devices (Optional)",
                    "refresh": "Refresh device list",
                    "update_interval": "Update interval (seconds)"
                }
            }
        },
        "error": {
            "cannot_connect": "Failed to connect to EZVIZ Cloud",
            "invalid_auth": "Invalid authentication",
            "no_devices": "No devices found in your account",
            "device_error": "Error retrieving devices"
        },
        "abort": {
            "already_configured": "EZVIZ Cloud is already configured"
        }
    },
    "options": {
        "step": {
            "init": {
                "title": "EZVIZ Cloud Options",
                "description": "Configure EZVIZ Cloud integration options. {refresh_tip}",
                "data": {
                    "devices": "Select devices to monitor",
                    "refresh": "Refresh device list",
                    "update_interval": "Update interval (seconds)",
                    "webhook_url": "WeCom Webhook URL"
                }
            }
        }
    }
}

ZH_TRANSLATIONS = {
    "config": {
        "step": {
            "user": {
                "title": "萤石云",
                "description": "设置萤石云集成",
                "data": {
                    "app_key": "App Key",
                    "app_secret": "App Secret"
                }
            },
            "webhook": {
                "title": "企业微信通知",
                "description": "配置企业微信机器人 Webhook URL 以接收隐私状态变更通知",
                "data": {
                    "webhook_url": "企业微信 Webhook URL (可选)"
                }
            },
            "devices": {
                "title": "选择设备",
                "description": "选择要监控的设备，您可以不选择任何设备，稍后再配置。{refresh_tip}",
                "data": {
                    "devices": "设备 (可选)",
                    "refresh": "刷新设备列表",
                    "update_interval": "更新间隔 (秒)"
                }
            }
        },
        "error": {
            "cannot_connect": "连接萤石云失败",
            "invalid_auth": "认证无效",
            "no_devices": "您的账户中未发现设备",
            "device_error": "获取设备时出错"
        },
        "abort": {
            "already_configured": "萤石云已经配置过了"
        }
    },
    "options": {
        "step": {
            "init": {
                "title": "萤石云选项",
                "description": "配置萤石云集成选项。{refresh_tip}",
                "data": {
                    "devices": "选择要监控的设备",
                    "refresh": "刷新设备列表",
                    "update_interval": "更新间隔 (秒)",
                    "webhook_url": "企业微信 Webhook URL"
                }
            }
        }
    }
}

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the EZVIZ Cloud component."""
    hass.data[DOMAIN] = {}

    # HomeKit优化和调试日志
    _LOGGER.info("Setting up EZVIZ Cloud integration with HomeKit Bridge optimizations")

    # 创建翻译文件目录
    translations_dir = Path(hass.config.path("custom_components", DOMAIN, "translations"))
    translations_dir.mkdir(parents=True, exist_ok=True)

    # 写入英文翻译文件
    en_json_path = translations_dir / "en.json"
    if not en_json_path.exists():
        with open(en_json_path, "w", encoding='utf-8') as f:
            json.dump(EN_TRANSLATIONS, f, indent=4, ensure_ascii=False)

    # 写入中文翻译文件
    zh_json_path = translations_dir / "zh-Hans.json"
    if not zh_json_path.exists():
        with open(zh_json_path, "w", encoding='utf-8') as f:
            json.dump(ZH_TRANSLATIONS, f, indent=4, ensure_ascii=False)

    # 写入strings.json文件
    strings_json_path = Path(hass.config.path("custom_components", DOMAIN, "strings.json"))
    if not strings_json_path.exists():
        with open(strings_json_path, "w", encoding='utf-8') as f:
            json.dump(EN_TRANSLATIONS, f, indent=4, ensure_ascii=False)

    # 注册HomeKit兼容的事件监听
    if HOMEKIT_SUPPORT_ENABLED:
        async def async_handle_privacy_event(event):
            """Handle privacy status changes for HomeKit Bridge compatibility."""
            device_sn = event.data.get("device_sn")
            new_status = event.data.get("new_status")

            _LOGGER.debug("Privacy event received for device %s: %s", device_sn, new_status)

            # 通知所有相关的entry
            for entry_id, entry_data in hass.data[DOMAIN].items():
                if isinstance(entry_data, dict) and "device_callbacks" in entry_data:
                    if device_sn in entry_data.get("devices", {}):
                        try:
                            callback_func = entry_data["device_callbacks"]
                            if callback_func:
                                await callback_func(device_sn, new_status)
                        except Exception as error:
                            _LOGGER.error("Error in device callback for %s: %s", device_sn, error)

        # 监听隐私状态变化事件
        hass.bus.async_listen(EVENT_PRIVACY_CHANGED, async_handle_privacy_event)
        _LOGGER.debug("HomeKit Bridge event listeners registered")

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up EZVIZ Cloud from a config entry with HomeKit Bridge optimizations."""
    app_key = entry.data.get(CONF_APP_KEY)
    app_secret = entry.data.get(CONF_APP_SECRET)
    webhook_url = entry.data.get(CONF_WEBHOOK_URL)

    session = async_get_clientsession(hass)

    try:
        # 创建API客户端
        ezviz_client = EzvizCloudChinaApi(
            app_key=app_key,
            app_secret=app_secret,
            session=session
        )

        # 测试连接
        await ezviz_client.get_token()
        _LOGGER.info("Successfully connected to EZVIZ Cloud API")

        # 存储客户端对象
        hass.data[DOMAIN][entry.entry_id] = {
            "client": ezviz_client,
            "devices": {},
            "webhook_url": webhook_url,
            "update_lock": asyncio.Lock(),
            "device_callbacks": None,  # 将由switch.py设置
            "last_update": None,  # 追踪最后更新时间
        }

        # 设置更新间隔
        update_interval = entry.options.get(
            CONF_UPDATE_INTERVAL,
            entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        )

        # 减少更新间隔以提高HomeKit响应性
        if update_interval > 60:
            update_interval = 30  # 限制最大更新间隔为30秒
            _LOGGER.info("Reduced update interval to %s seconds for better HomeKit compatibility", update_interval)

        # 设置定期更新
        async def async_update_devices(now=None):
            """Update all device states with error handling."""
            try:
                await update_devices(hass, entry)
            except Exception as error:
                _LOGGER.error("Error during scheduled device update: %s", error)

        entry.async_on_unload(
            async_track_time_interval(
                hass, async_update_devices, timedelta(seconds=update_interval)
            )
        )

        # 首次更新设备状态
        await update_devices(hass, entry)

        # 注册服务
        register_services(hass)

        # 设置平台
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        _LOGGER.info("EZVIZ Cloud integration setup completed for entry %s", entry.entry_id)
        return True

    except Exception as error:
        _LOGGER.error("Failed to initialize EZVIZ client: %s", error)
        raise ConfigEntryNotReady from error

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.info("Unloading EZVIZ Cloud integration entry %s", entry.entry_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # 清理数据
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})

        # 关闭客户端会话
        client = entry_data.get("client")
        if client and hasattr(client, "session") and client.session:
            try:
                await client.session.close()
            except Exception as error:
                _LOGGER.warning("Error closing client session: %s", error)

    _LOGGER.info("EZVIZ Cloud integration unloaded: %s", unload_ok)
    return unload_ok

async def update_devices(hass: HomeAssistant, entry: ConfigEntry):
    """Update devices status and notify on changes with HomeKit optimizations."""
    ezviz_data = hass.data[DOMAIN][entry.entry_id]
    client = ezviz_data["client"]
    webhook_url = ezviz_data.get("webhook_url")
    configured_devices = entry.data.get(CONF_DEVICES, [])
    update_lock = ezviz_data["update_lock"]

    # 如果没有配置任何设备，则跳过更新
    if not configured_devices:
        _LOGGER.debug("No devices configured, skipping update")
        return

    # 使用锁防止并发更新
    async with update_lock:
        try:
            import time
            start_time = time.time()

            # 获取设备列表
            devices = await client.get_devices()

            # 确保devices是列表
            if not isinstance(devices, list):
                _LOGGER.error("Expected device list but got %s", type(devices))
                return

            device_count = 0
            status_changes = 0

            for device in devices:
                # 确保device是字典
                if not isinstance(device, dict):
                    continue

                device_sn = device.get("deviceSerial")
                # 只处理已配置的设备
                if device_sn and device_sn in configured_devices:
                    device_count += 1

                    # 获取设备隐私状态
                    try:
                        privacy_enabled = await client.get_privacy_status(device_sn)
                        privacy_status = PRIVACY_ON if privacy_enabled else PRIVACY_OFF
                    except EzvizCloudChinaApiError as error:
                        # 设备可能不支持隐私模式
                        _LOGGER.warning("Device %s may not support privacy mode: %s", device_sn, error)
                        privacy_status = PRIVACY_OFF

                    # 保存设备状态
                    if device_sn not in ezviz_data["devices"]:
                        ezviz_data["devices"][device_sn] = {
                            "privacy_status": privacy_status,
                            "info": device,
                        }
                        _LOGGER.debug("Added new device %s with status %s", device_sn, privacy_status)
                    else:
                        old_status = ezviz_data["devices"][device_sn]["privacy_status"]
                        if old_status != privacy_status:
                            # 状态变化，触发事件
                            status_changes += 1
                            _LOGGER.info(
                                "Privacy mode changed for device %s: %s -> %s",
                                device_sn,
                                old_status,
                                privacy_status,
                            )

                            # 更新存储的状态
                            ezviz_data["devices"][device_sn]["privacy_status"] = privacy_status

                            # 处理状态变化回调 (用于HomeKit实时更新)
                            if ezviz_data["device_callbacks"]:
                                try:
                                    await ezviz_data["device_callbacks"](device_sn, privacy_status)
                                except Exception as callback_error:
                                    _LOGGER.error("Error in device callback for %s: %s", device_sn, callback_error)

                            # 触发事件
                            hass.bus.async_fire(
                                EVENT_PRIVACY_CHANGED,
                                {
                                    "device_sn": device_sn,
                                    "device_name": device.get("deviceName", device_sn),
                                    "old_status": old_status,
                                    "new_status": privacy_status,
                                },
                            )

                            # 发送webhook通知
                            if webhook_url:
                                try:
                                    await send_webhook_notification(
                                        hass,
                                        webhook_url,
                                        device_sn,
                                        device.get("deviceName", device_sn),
                                        old_status,
                                        privacy_status,
                                    )
                                except Exception as webhook_error:
                                    _LOGGER.error("Error sending webhook notification: %s", webhook_error)

                        # 更新设备信息
                        ezviz_data["devices"][device_sn]["info"] = device

            # 记录更新统计
            end_time = time.time()
            ezviz_data["last_update"] = end_time

            _LOGGER.debug(
                "Device update completed: %d devices processed, %d status changes, %.2fs elapsed",
                device_count, status_changes, end_time - start_time
            )

        except Exception as error:
            _LOGGER.error("Failed to update EZVIZ devices: %s", error)

async def send_webhook_notification(hass, webhook_url, device_sn, device_name, old_status, new_status):
    """Send webhook notification to WeCom with error handling."""
    import aiohttp
    from datetime import datetime

    session = async_get_clientsession(hass)

    # 企业微信机器人消息格式 - 改为text类型
    message = {
        "msgtype": "text",
        "text": {
            "content": f"萤石设备隐私状态变更通知\n"
                       f"设备名称: {device_name}\n"
                       f"设备SN: {device_sn}\n"
                       f"状态变更: {old_status} → {new_status}\n"
                       f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)  # 10秒超时
        async with session.post(
                webhook_url,
                json=message,
                headers={"Content-Type": "application/json"},
                timeout=timeout
        ) as response:
            if response.status != 200:
                response_text = await response.text()
                _LOGGER.error(
                    "Failed to send webhook notification: %s - %s",
                    response.status,
                    response_text,
                )
            else:
                _LOGGER.info("Successfully sent webhook notification for device %s", device_sn)
    except asyncio.TimeoutError:
        _LOGGER.error("Webhook notification timed out for device %s", device_sn)
    except Exception as error:
        _LOGGER.error("Error sending webhook notification: %s", error)

def register_services(hass):
    """Register services for EZVIZ Cloud integration with enhanced error handling."""
    from homeassistant.helpers import config_validation as cv

    async def async_set_privacy_mode(call):
        """Set privacy mode for a device with HomeKit compatibility."""
        device_sn = call.data.get("device_sn")
        privacy_mode = call.data.get("privacy_mode")

        _LOGGER.debug("Service call: set_privacy_mode for device %s to %s", device_sn, privacy_mode)

        success = False
        for entry_id, ezviz_data in hass.data[DOMAIN].items():
            if isinstance(ezviz_data, dict) and "client" in ezviz_data:
                client = ezviz_data["client"]
                if device_sn in ezviz_data.get("devices", {}):
                    try:
                        # 调用API设置隐私模式
                        enable = privacy_mode == "on"
                        api_success = await client.set_privacy(device_sn, enable)

                        if api_success:
                            # 立即更新设备状态以确保同步
                            config_entry = hass.config_entries.async_get_entry(entry_id)
                            if config_entry:
                                await update_devices(hass, config_entry)
                            success = True
                            _LOGGER.info("Successfully set privacy mode for device %s to %s", device_sn, privacy_mode)
                            break
                        else:
                            _LOGGER.error("API call failed to set privacy mode for device %s", device_sn)
                    except Exception as error:
                        _LOGGER.error("Error setting privacy mode for device %s: %s", device_sn, error)

        if not success:
            if device_sn:
                _LOGGER.error("Device %s not found or operation failed", device_sn)
            else:
                _LOGGER.error("No device_sn provided in service call")

        return success

    # 检查服务是否已经注册
    if not hass.services.has_service(DOMAIN, "set_privacy_mode"):
        hass.services.async_register(
            DOMAIN,
            "set_privacy_mode",
            async_set_privacy_mode,
            schema=vol.Schema(
                {
                    vol.Required("device_sn"): cv.string,
                    vol.Required("privacy_mode"): vol.In(["on", "off"]),
                }
            ),
        )
        _LOGGER.debug("Registered set_privacy_mode service")
    else:
        _LOGGER.debug("Service set_privacy_mode already registered")