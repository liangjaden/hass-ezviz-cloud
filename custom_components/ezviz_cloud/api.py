"""API client for EZVIZ Cloud China."""
import logging
import time
from typing import Dict, List, Any, Optional, Union

import aiohttp
from aiohttp import ClientSession

_LOGGER = logging.getLogger(__name__)

# API Endpoints
API_BASE_URL = "https://open.ys7.com/api"
API_GET_TOKEN = f"{API_BASE_URL}/lapp/token/get"
API_GET_DEVICES = f"{API_BASE_URL}/lapp/device/list"
API_GET_DEVICE_INFO = f"{API_BASE_URL}/lapp/device/info"
API_GET_PRIVACY_STATUS = f"{API_BASE_URL}/lapp/device/scene/switch/status"
API_SET_PRIVACY = f"{API_BASE_URL}/lapp/device/scene/switch/set"
API_GET_DEVICE_CAPTURE = f"{API_BASE_URL}/lapp/device/capture"
API_GET_LIVE_ADDRESS = f"{API_BASE_URL}/lapp/live/address/get"


class EzvizCloudChinaApiError(Exception):
    """Exception for EZVIZ Cloud China API errors."""
    pass


class EzvizCloudChinaApi:
    """Client for EZVIZ Cloud China API."""

    def __init__(self, app_key: str, app_secret: str, session: ClientSession = None):
        """Initialize the API client."""
        self.app_key = app_key
        self.app_secret = app_secret
        self.session = session
        self.access_token = None
        self.token_expires_at = 0
        self.default_headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }

    async def _request(self, url: str, method: str = "POST", params: Dict = None) -> Dict[str, Any]:
        """Make a request to the API."""
        if not self.session:
            self.session = aiohttp.ClientSession()

        if params is None:
            params = {}

        # Add access token if not getting a token
        if url != API_GET_TOKEN and self.access_token:
            params["accessToken"] = self.access_token

        _LOGGER.debug(f"Making {method} request to {url} with params: {params}")

        try:
            async with self.session.request(
                    method, url, data=params, headers=self.default_headers
            ) as resp:
                data = await resp.json()
                if data.get("code") != "200":
                    error_msg = f"API error: {data.get('code')} - {data.get('msg')}"
                    _LOGGER.error(error_msg)
                    raise EzvizCloudChinaApiError(error_msg)
                return data.get("data", {})
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Request error: {err}")
            raise EzvizCloudChinaApiError(f"Request failed: {err}")
        except Exception as err:
            _LOGGER.error(f"Unexpected error: {err}")
            raise EzvizCloudChinaApiError(f"Request failed: {err}")

    async def ensure_token_valid(self) -> str:
        """Ensure the access token is valid, refreshing if needed."""
        current_time = int(time.time() * 1000)  # Convert to milliseconds

        # If token is missing or will expire in the next hour, refresh it
        if (not self.access_token or
                current_time > (self.token_expires_at - 3600000)):  # 1 hour margin
            await self.get_token()

        return self.access_token

    async def get_token(self) -> str:
        """Get a new access token."""
        params = {
            "appKey": self.app_key,
            "appSecret": self.app_secret
        }

        data = await self._request(API_GET_TOKEN, "POST", params)

        self.access_token = data.get("accessToken")
        self.token_expires_at = data.get("expireTime")

        if not self.access_token:
            raise EzvizCloudChinaApiError("Failed to get access token")

        _LOGGER.debug(f"Got new access token, expires at: {self.token_expires_at}")
        return self.access_token

    async def get_devices(self) -> List[Dict[str, Any]]:
        """Get a list of devices."""
        await self.ensure_token_valid()

        params = {
            "pageStart": 0,
            "pageSize": 50,  # Adjust as needed
        }

        try:
            data = await self._request(API_GET_DEVICES, "POST", params)
            # 有些API版本返回的是一个列表，有些是一个包含deviceInfos的字典
            if isinstance(data, dict) and "deviceInfos" in data:
                return data.get("deviceInfos", [])
            elif isinstance(data, list):
                return data
            else:
                _LOGGER.warning(f"Unexpected device data format: {data}")
                return []
        except EzvizCloudChinaApiError:
            _LOGGER.error("Error getting devices list, returning empty list")
            return []

    async def get_device_info(self, device_serial: str) -> Dict[str, Any]:
        """Get information about a specific device."""
        await self.ensure_token_valid()

        params = {
            "deviceSerial": device_serial
        }

        return await self._request(API_GET_DEVICE_INFO, "POST", params)

    async def get_privacy_status(self, device_serial: str, channel_no: int = 1) -> bool:
        """Get the privacy mode status of a device."""
        await self.ensure_token_valid()

        params = {
            "deviceSerial": device_serial,
        }

        try:
            data = await self._request(API_GET_PRIVACY_STATUS, "POST", params)
            # Privacy status: 0-off, 1-on
            return data.get("enable") == 1
        except EzvizCloudChinaApiError:
            # Device might not support privacy mode
            _LOGGER.warning(f"Device {device_serial} may not support privacy mode")
            return False

    async def set_privacy(self, device_serial: str, enable: bool, channel_no: int = 1) -> bool:
        """Set the privacy mode of a device."""
        await self.ensure_token_valid()

        params = {
            "deviceSerial": device_serial,
            "enable": 1 if enable else 0,
            "channelNo": channel_no
        }

        try:
            await self._request(API_SET_PRIVACY, "POST", params)
            return True
        except EzvizCloudChinaApiError as err:
            _LOGGER.error(f"Failed to set privacy mode: {err}")
            return False

    async def get_device_capture(self, device_serial: str, channel_no: int = 1) -> bytes:
        """Get a snapshot from the device."""
        await self.ensure_token_valid()

        # For image captures, we need to handle the response differently
        try:
            url = f"{API_GET_DEVICE_CAPTURE}?accessToken={self.access_token}&deviceSerial={device_serial}&channelNo={channel_no}"

            if not self.session:
                self.session = aiohttp.ClientSession()

            async with self.session.get(url) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    _LOGGER.error(f"Failed to get device capture: {error_text}")
                    raise EzvizCloudChinaApiError(f"Failed to get device capture: {resp.status}")

                content_type = resp.headers.get("Content-Type", "")
                # 检查是否是图片响应
                if "image" in content_type:
                    return await resp.read()
                else:
                    # 可能返回了错误信息的JSON
                    error_text = await resp.text()
                    _LOGGER.error(f"Expected image but got: {error_text}")
                    raise EzvizCloudChinaApiError(f"Invalid capture response: {error_text}")
        except aiohttp.ClientError as err:
            _LOGGER.error(f"Failed to get device capture: {err}")
            raise EzvizCloudChinaApiError(f"Failed to get device capture: {err}")
        except Exception as err:
            _LOGGER.error(f"Failed to get device capture: {err}")
            raise EzvizCloudChinaApiError(f"Failed to get device capture: {err}")

    async def get_live_stream_url(self, device_serial: str, channel_no: int = 1,
                                  protocol: str = "ezopen", quality: int = 2) -> str:
        """Get the live stream URL for a device."""
        await self.ensure_token_valid()

        params = {
            "deviceSerial": device_serial,
            "channelNo": channel_no,
            "protocol": protocol,  # ezopen, rtsp, hls, etc.
            "quality": quality,    # 1: HD, 2: SD, etc.
            "expireTime": 86400    # URL validity in seconds (24 hours)
        }

        data = await self._request(API_GET_LIVE_ADDRESS, "POST", params)
        return data.get("url", "")

    async def get_rtsp_stream_url(self, device_serial: str, channel_no: int = 1, quality: int = 2) -> str:
        """Get the RTSP stream URL specifically."""
        await self.ensure_token_valid()

        params = {
            "deviceSerial": device_serial,
            "channelNo": channel_no,
            "protocol": "rtsp",
            "quality": quality,    # 1: HD, 2: SD, etc.
            "expireTime": 86400    # URL validity in seconds (24 hours)
        }

        try:
            data = await self._request(API_GET_LIVE_ADDRESS, "POST", params)
            rtsp_url = data.get("url", "")
            _LOGGER.debug(f"Got RTSP URL for device {device_serial}: {rtsp_url}")
            return rtsp_url
        except EzvizCloudChinaApiError as err:
            _LOGGER.error(f"Failed to get RTSP URL: {err}")
            return ""