"""Config flow for EZVIZ Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    OptionsFlow,
    ConfigEntry,
    CONN_CLASS_CLOUD_POLL
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, aiohttp_client
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_APP_KEY,
    CONF_APP_SECRET,
    CONF_DEVICES,
    CONF_DEVICE_SN,
    CONF_DEVICE_NAME,
    CONF_WEBHOOK_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)
from .api import EzvizCloudChinaApi, EzvizCloudChinaApiError

_LOGGER = logging.getLogger(__name__)


class EzvizCloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EZVIZ Cloud."""

    VERSION = 1
    CONNECTION_CLASS = CONN_CLASS_CLOUD_POLL

    def __init__(self):
        """Initialize the config flow."""
        self.app_key = None
        self.app_secret = None
        self.client = None
        self.webhook_url = None
        self.device_options = {}
        self.available_devices = []

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            app_key = user_input[CONF_APP_KEY]
            app_secret = user_input[CONF_APP_SECRET]

            session = aiohttp_client.async_get_clientsession(self.hass)

            try:
                # 使用中国版萤石云API
                client = EzvizCloudChinaApi(
                    app_key=app_key,
                    app_secret=app_secret,
                    session=session
                )

                # 测试连接
                await client.get_token()

                # 登录成功，保存数据并进入下一步
                self.app_key = app_key
                self.app_secret = app_secret
                self.client = client

                return await self.async_step_webhook()

            except EzvizCloudChinaApiError as error:
                _LOGGER.error("Failed to connect to EZVIZ: %s", error)
                errors["base"] = "cannot_connect"
            except Exception as error:
                _LOGGER.exception("Unexpected error: %s", error)
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_APP_KEY): str,
                    vol.Required(CONF_APP_SECRET): str,
                }
            ),
            errors=errors,
        )

    async def async_step_webhook(self, user_input=None) -> FlowResult:
        """Configure webhook for notification."""
        if user_input is not None:
            webhook_url = user_input.get(CONF_WEBHOOK_URL)

            # 保存webhook URL并进入设备选择步骤
            self.webhook_url = webhook_url

            return await self.async_step_devices()

        return self.async_show_form(
            step_id="webhook",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_WEBHOOK_URL): str,
                }
            ),
        )

    async def _fetch_devices(self):
        """Fetch devices from API and update device options."""
        self.device_options = {}
        try:
            # 获取设备列表
            self.available_devices = await self.client.get_devices()

            for device in self.available_devices:
                device_sn = device.get("deviceSerial")
                device_name = device.get("deviceName", device_sn)
                if device_sn:
                    self.device_options[device_sn] = f"{device_name} ({device_sn})"

            return True
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("Failed to get EZVIZ devices: %s", error)
            return False
        except Exception as error:
            _LOGGER.exception("Unexpected error fetching devices: %s", error)
            return False

    async def async_step_devices(self, user_input=None) -> FlowResult:
        """Select devices to monitor."""
        errors = {}

        # 如果是刷新操作
        if user_input is not None and user_input.get("refresh", False):
            if not await self._fetch_devices():
                errors["base"] = "device_error"
            return await self.async_step_devices()

        # 第一次进入或者提交设备选择
        if not self.device_options:
            if not await self._fetch_devices():
                errors["base"] = "device_error"

        if not self.device_options and not errors:
            errors["base"] = "no_devices"

        if user_input is not None and not errors and not user_input.get("refresh", False):
            selected_devices = user_input.get(CONF_DEVICES, [])
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

            # 保存配置 - 设备可以是空列表，表示不监控任何设备
            return self.async_create_entry(
                title=f"萤石云 ({len(selected_devices)} 台设备)",
                data={
                    CONF_APP_KEY: self.app_key,
                    CONF_APP_SECRET: self.app_secret,
                    CONF_WEBHOOK_URL: getattr(self, "webhook_url", None),
                    CONF_DEVICES: selected_devices,
                    CONF_UPDATE_INTERVAL: update_interval,
                },
            )

        # 添加刷新设备按钮和可选设备选择
        schema = vol.Schema({
            vol.Optional("refresh", default=False): bool,
            vol.Optional(CONF_DEVICES, default=[]): cv.multi_select(self.device_options),
            vol.Optional(
                CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
            ): vol.All(vol.Coerce(int), vol.Range(min=10)),
        })

        return self.async_show_form(
            step_id="devices",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "refresh_tip": "选中刷新设备列表并点击提交来刷新设备列表"
            }
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> EzvizOptionsFlowHandler:
        """Get the options flow for this handler."""
        return EzvizOptionsFlowHandler(config_entry)


class EzvizOptionsFlowHandler(OptionsFlow):
    """Handle EZVIZ options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        self.config_entry = config_entry
        self.client = None
        self.device_options = {}
        self.available_devices = []

    async def _fetch_devices(self, app_key, app_secret):
        """Fetch devices from API and update device options."""
        self.device_options = {}
        session = aiohttp_client.async_get_clientsession(self.hass)

        try:
            # 创建API客户端
            self.client = EzvizCloudChinaApi(
                app_key=app_key,
                app_secret=app_secret,
                session=session
            )

            # 获取设备列表
            self.available_devices = await self.client.get_devices()

            for device in self.available_devices:
                device_sn = device.get("deviceSerial")
                device_name = device.get("deviceName", device_sn)
                if device_sn:
                    self.device_options[device_sn] = f"{device_name} ({device_sn})"

            return True
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("Failed to get EZVIZ devices in options flow: %s", error)
            return False
        except Exception as error:
            _LOGGER.exception("Unexpected error fetching devices in options flow: %s", error)
            return False

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        errors = {}
        app_key = self.config_entry.data.get(CONF_APP_KEY)
        app_secret = self.config_entry.data.get(CONF_APP_SECRET)
        current_devices = self.config_entry.data.get(CONF_DEVICES, [])

        # 如果是刷新操作
        if user_input is not None and user_input.get("refresh", False):
            if not await self._fetch_devices(app_key, app_secret):
                errors["base"] = "device_error"
            return await self.async_step_init()

        # 确保已加载设备列表
        if not self.device_options:
            if not await self._fetch_devices(app_key, app_secret):
                errors["base"] = "device_error"

        if user_input is not None and not errors and not user_input.get("refresh", False):
            selected_devices = user_input.get(CONF_DEVICES, [])
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
            webhook_url = user_input.get(CONF_WEBHOOK_URL, self.config_entry.data.get(CONF_WEBHOOK_URL, ""))

            # 更新config entry数据
            new_data = {**self.config_entry.data}
            new_data[CONF_DEVICES] = selected_devices

            # 创建新选项
            new_options = {
                CONF_UPDATE_INTERVAL: update_interval,
                CONF_WEBHOOK_URL: webhook_url,
            }

            # 更新config entry
            self.hass.config_entries.async_update_entry(
                entry=self.config_entry,
                data=new_data,
                options=new_options
            )

            return self.async_create_entry(title="", data={})

        # 添加刷新设备按钮和设备选择
        schema = vol.Schema({
            vol.Optional("refresh", default=False): bool,
            vol.Optional(CONF_DEVICES, default=current_devices): cv.multi_select(self.device_options),
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=self.config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=10)),
            vol.Optional(
                CONF_WEBHOOK_URL,
                default=self.config_entry.data.get(CONF_WEBHOOK_URL, ""),
            ): str,
        })

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "refresh_tip": "选中刷新设备列表并点击提交来刷新设备列表"
            }
        )