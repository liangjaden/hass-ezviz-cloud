"""The EZVIZ Cloud integration."""
import asyncio
import logging
import json
from datetime import timedelta
from pathlib import Path

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, Platform

from pyezviz import EzvizClient, EzvizError

from .const import (
    DOMAIN,
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_DEVICES,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    EVENT_PRIVACY_CHANGED,
    CONF_WEBHOOK_URL,
)
from .card import async_setup_cards

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.CAMERA, Platform.SWITCH, Platform.BINARY_SENSOR]

# 翻译文件内容
EN_TRANSLATIONS = {
    "config": {
        "step": {
            "user": {
                "title": "EZVIZ Cloud",
                "description": "Set up EZVIZ Cloud integration",
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
                "description": "Select the devices you want to monitor",
                "data": {
                    "devices": "Devices",
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
                "description": "Configure EZVIZ Cloud integration options",
                "data": {
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
                "description": "选择要监控的设备",
                "data": {
                    "devices": "设备",
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
                "description": "配置萤石云集成选项",
                "data": {
                    "update_interval": "更新间隔 (秒)",
                    "webhook_url": "企业微信 Webhook URL"
                }
            }
        }
    }
}

# 创建自定义图标
EZVIZ_ICON_SVG = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <path d="M12,2 C17.523,2 22,6.477 22,12 C22,17.523 17.523,22 12,22 C6.477,22 2,17.523 2,12 C2,6.477 6.477,2 12,2 Z" fill="#0096D6"/>
  <path d="M12,5 C13.105,5 14,5.895 14,7 C14,8.105 13.105,9 12,9 C10.895,9 10,8.105 10,7 C10,5.895 10.895,5 12,5 Z M12,10 C14.761,10 17,12.239 17,15 L17,16 C17,16.552 16.552,17 16,17 L8,17 C7.448,17 7,16.552 7,16 L7,15 C7,12.239 9.239,10 12,10 Z" fill="#FFFFFF"/>
</svg>
"""

def create_icons(hass):
    """Create custom icons for EZVIZ integration."""
    # 确保自定义图标目录存在
    icons_dir = Path(hass.config.path("www", DOMAIN, "icons"))
    icons_dir.mkdir(parents=True, exist_ok=True)

    # 写入图标文件
    icon_path = icons_dir / "ezviz.svg"
    if not icon_path.exists():
        with open(icon_path, "w") as icon_file:
            icon_file.write(EZVIZ_ICON_SVG)

async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the EZVIZ Cloud component."""
    hass.data[DOMAIN] = {}

    # 创建图标
    create_icons(hass)

    # 设置自定义卡片
    await async_setup_cards(hass)

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

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up EZVIZ Cloud from a config entry."""
    app_key = entry.data.get(CONF_APP_KEY)
    app_secret = entry.data.get(CONF_APP_SECRET)
    webhook_url = entry.data.get(CONF_WEBHOOK_URL)

    session = async_get_clientsession(hass)

    try:
        ezviz_client = EzvizClient(app_key, app_secret, session=session)
        await hass.async_add_executor_job(ezviz_client.login)

        # 存储客户端对象
        hass.data[DOMAIN][entry.entry_id] = {
            "client": ezviz_client,
            "devices": {},
            "webhook_url": webhook_url,
        }

        # 定期更新设备状态
        update_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

        # 设置定期更新
        async def async_update_devices(now=None):
            """Update all device states."""
            await update_devices(hass, entry)

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

        return True

    except EzvizError as error:
        _LOGGER.error("Failed to initialize EZVIZ client: %s", error)
        raise ConfigEntryNotReady from error

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

async def update_devices(hass, entry):
    """Update devices status and notify on changes."""
    ezviz_data = hass.data[DOMAIN][entry.entry_id]
    client = ezviz_data["client"]
    webhook_url = ezviz_data["webhook_url"]

    try:
        # 获取设备列表
        devices = await hass.async_add_executor_job(client.get_devices)

        for device in devices:
            device_sn = device.get("device_serial")
            if device_sn:
                # 获取设备详情
                device_info = await hass.async_add_executor_job(
                    client.get_device_info, device_sn
                )

                # 检查隐私模式状态
                privacy_status = device_info.get("privacy_status", "unknown")

                # 保存设备状态
                if device_sn not in ezviz_data["devices"]:
                    ezviz_data["devices"][device_sn] = {
                        "privacy_status": privacy_status,
                        "info": device_info,
                    }
                else:
                    old_status = ezviz_data["devices"][device_sn]["privacy_status"]
                    if old_status != privacy_status:
                        # 状态变化，触发事件
                        _LOGGER.info(
                            "Privacy mode changed for device %s: %s -> %s",
                            device_sn,
                            old_status,
                            privacy_status,
                        )

                        # 更新存储的状态
                        ezviz_data["devices"][device_sn]["privacy_status"] = privacy_status

                        # 触发事件
                        hass.bus.async_fire(
                            EVENT_PRIVACY_CHANGED,
                            {
                                "device_sn": device_sn,
                                "old_status": old_status,
                                "new_status": privacy_status,
                            },
                        )

                        # 发送webhook通知
                        if webhook_url:
                            await send_webhook_notification(
                                hass,
                                webhook_url,
                                device_sn,
                                device_info.get("device_name", device_sn),
                                old_status,
                                privacy_status,
                            )

                    # 更新设备信息
                    ezviz_data["devices"][device_sn]["info"] = device_info

    except EzvizError as error:
        _LOGGER.error("Failed to update EZVIZ devices: %s", error)

async def send_webhook_notification(hass, webhook_url, device_sn, device_name, old_status, new_status):
    """Send webhook notification to WeCom."""
    import aiohttp
    import json
    from datetime import datetime

    session = async_get_clientsession(hass)

    # 企业微信机器人消息格式
    message = {
        "msgtype": "markdown",
        "markdown": {
            "content": f"### 萤石设备隐私状态变更通知\n"
                       f"> **设备名称**: {device_name}\n"
                       f"> **设备SN**: {device_sn}\n"
                       f"> **状态变更**: {old_status} → {new_status}\n"
                       f"> **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        }
    }

    try:
        async with session.post(
                webhook_url, json=message, headers={"Content-Type": "application/json"}
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
    except Exception as error:
        _LOGGER.error("Error sending webhook notification: %s", error)

def register_services(hass):
    """Register services for EZVIZ Cloud integration."""
    from homeassistant.helpers import config_validation as cv

    async def async_set_privacy_mode(call):
        """Set privacy mode for a device."""
        device_sn = call.data.get("device_sn")
        privacy_mode = call.data.get("privacy_mode")

        for entry_id, ezviz_data in hass.data[DOMAIN].items():
            client = ezviz_data["client"]
            if device_sn in ezviz_data["devices"]:
                try:
                    # 设置隐私模式
                    if privacy_mode == "on":
                        await hass.async_add_executor_job(
                            client.enable_privacy_mode, device_sn
                        )
                    else:
                        await hass.async_add_executor_job(
                            client.disable_privacy_mode, device_sn
                        )

                    # 立即更新设备状态
                    await update_devices(hass, hass.config_entries.async_get_entry(entry_id))

                    return True
                except EzvizError as error:
                    _LOGGER.error(
                        "Failed to set privacy mode for device %s: %s", device_sn, error
                    )
                    return False

        _LOGGER.error("Device %s not found", device_sn)
        return False

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