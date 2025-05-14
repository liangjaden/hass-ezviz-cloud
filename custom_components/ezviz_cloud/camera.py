"""Support for EZVIZ Cloud cameras."""
import logging
import asyncio
from typing import Optional

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_DEVICES
from .api import EzvizCloudChinaApiError

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up EZVIZ cameras based on a config entry."""
    ezviz_data = hass.data[DOMAIN][entry.entry_id]
    client = ezviz_data["client"]
    devices = ezviz_data["devices"]

    # 获取配置的设备
    configured_devices = entry.data.get(CONF_DEVICES, [])
    if not configured_devices:
        _LOGGER.info("No devices configured for cameras, skipping setup")
        return

    cameras = []
    for device_sn in configured_devices:
        if device_sn in devices:
            cameras.append(EzvizCamera(hass, entry.entry_id, device_sn))

    async_add_entities(cameras, True)

class EzvizCamera(Camera):
    """An implementation of a EZVIZ camera."""

    def __init__(self, hass, entry_id, device_sn):
        """Initialize a EZVIZ camera."""
        super().__init__()
        self.hass = hass
        self.entry_id = entry_id
        self.device_sn = device_sn

        self._client = hass.data[DOMAIN][entry_id]["client"]
        self._attr_name = None
        self._attr_unique_id = f"{device_sn}_camera"
        self._attr_motion_detection_enabled = False
        self._stream_source = None
        self._rtsp_source = None
        self._last_image = None

        # 支持流式功能
        self._attr_supported_features = CameraEntityFeature.STREAM

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information about this EZVIZ camera."""
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
    def name(self):
        """Return the name of this camera."""
        device_info = self.hass.data[DOMAIN][self.entry_id]["devices"].get(self.device_sn, {}).get("info", {})
        return device_info.get("deviceName", self.device_sn)

    async def async_camera_image(self, width: Optional[int] = None, height: Optional[int] = None) -> Optional[bytes]:
        """Return a still image from the camera."""
        try:
            # 使用中国API获取图像
            self._last_image = await self._client.get_device_capture(self.device_sn)
            return self._last_image
        except EzvizCloudChinaApiError as error:
            _LOGGER.error("Failed to get camera image: %s", error)
            return self._last_image  # 返回上一次成功的图像，如果有的话
        except Exception as ex:
            _LOGGER.error("Unexpected error getting camera image: %s", ex)
            return self._last_image  # 返回上一次成功的图像，如果有的话

    async def async_stream_source(self):
        """Return the stream source."""
        # 尝试获取RTSP流URL
        if not self._rtsp_source:
            try:
                self._rtsp_source = await self._client.get_rtsp_stream_url(self.device_sn)
                if self._rtsp_source:
                    _LOGGER.info(f"Using RTSP stream for device {self.device_sn}: {self._rtsp_source}")
                    return self._rtsp_source
            except EzvizCloudChinaApiError as error:
                _LOGGER.warning(f"Failed to get RTSP stream, falling back to default stream: {error}")

        # 如果RTSP不可用，尝试获取默认流
        if not self._stream_source:
            try:
                self._stream_source = await self._client.get_live_stream_url(self.device_sn)
                _LOGGER.info(f"Using default stream for device {self.device_sn}: {self._stream_source}")
                return self._stream_source
            except EzvizCloudChinaApiError as error:
                _LOGGER.error(f"Failed to get any stream source: {error}")
                return None

        # 如果已经有stream_source，直接返回
        return self._stream_source if not self._rtsp_source else self._rtsp_source