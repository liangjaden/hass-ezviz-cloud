"""Config flow for EZVIZ Cloud integration."""
import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv, aiohttp_client
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from pyezviz import EzvizClient, EzvizError

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

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class EzvizCloudConfigFlow(config_entries.ConfigFlow):
    """Handle a config flow for EZVIZ Cloud."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self.app_key = None
        self.app_secret = None
        self.client = None
        self.webhook_url = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            app_key = user_input[CONF_APP_KEY]
            app_secret = user_input[CONF_APP_SECRET]

            session = aiohttp_client.async_get_clientsession(self.hass)

            try:
                client = EzvizClient(app_key, app_secret, session=session)
                await self.hass.async_add_executor_job(client.login)

                # 登录成功，保存数据并进入下一步
                self.app_key = app_key
                self.app_secret = app_secret
                self.client = client

                return await self.async_step_webhook()

            except EzvizError as error:
                _LOGGER.error("Failed to connect to EZVIZ: %s", error)
                errors["base"] = "cannot_connect"

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

    async def async_step_devices(self, user_input=None) -> FlowResult:
        """Select devices to monitor."""
        errors = {}
        device_options = {}

        try:
            # 获取设备列表
            devices = await self.hass.async_add_executor_job(self.client.get_devices)

            for device in devices:
                device_sn = device.get("device_serial")
                device_name = device.get("device_name", device_sn)
                if device_sn:
                    device_options[device_sn] = f"{device_name} ({device_sn})"

            if not device_options:
                errors["base"] = "no_devices"

        except EzvizError as error:
            _LOGGER.error("Failed to get EZVIZ devices: %s", error)
            errors["base"] = "device_error"

        if user_input is not None and not errors:
            selected_devices = user_input.get(CONF_DEVICES, [])
            update_interval = user_input.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)

            # 保存配置
            return self.async_create_entry(
                title=f"EZVIZ Cloud ({len(selected_devices)} devices)",
                data={
                    CONF_APP_KEY: self.app_key,
                    CONF_APP_SECRET: self.app_secret,
                    CONF_WEBHOOK_URL: getattr(self, "webhook_url", None),
                    CONF_DEVICES: selected_devices,
                    CONF_UPDATE_INTERVAL: update_interval,
                },
            )

        return self.async_show_form(
            step_id="devices",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DEVICES): cv.multi_select(device_options),
                    vol.Optional(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(vol.Coerce(int), vol.Range(min=10)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EzvizOptionsFlowHandler(config_entry)


class EzvizOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle EZVIZ options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=10)),
                    vol.Optional(
                        CONF_WEBHOOK_URL,
                        default=self.config_entry.data.get(CONF_WEBHOOK_URL, ""),
                    ): str,
                }
            ),
        )