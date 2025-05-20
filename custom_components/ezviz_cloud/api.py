"""API client for EZVIZ Cloud China."""
import logging
import time
import asyncio
from typing import Dict, List, Any, Optional, Union

import aiohttp
from aiohttp import ClientSession, ClientTimeout

from .const import API_TIMEOUT, API_RETRY_ATTEMPTS

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
        self._token_lock = asyncio.Lock()  # 令牌获取锁
        self._retry_backoff = [1, 2, 5]  # 重试间隔（秒）

    async def _request(self, url: str, method: str = "POST", params: Dict = None, retry_count: int = 0) -> Dict[str, Any]:
        """Make a request to the API with retry logic."""
        if not self.session:
            self.session = aiohttp.ClientSession(timeout=ClientTimeout(total=API_TIMEOUT))

        if params is None:
            params = {}

        # Add access token if not getting a token
        if url != API_GET_TOKEN and self.access_token:
            params["accessToken"] = self.access_token

        _LOGGER.debug(f"Making {method} request to {url} with params: {params}")

        try:
            async with self.session.request(
                    method, url, data=params, headers=self.default_headers,
                    timeout=ClientTimeout(total=API_TIMEOUT)
            ) as resp:
                # 处理HTTP错误
                if resp.status != 200:
                    error_msg = f"HTTP error: {resp.status}"
                    _LOGGER.error(error_msg)
                    # 如果有重试次数，进行重试
                    if retry_count < API_RETRY_ATTEMPTS:
                        backoff_time = self._retry_backoff[min(retry_count, len(self._retry_backoff) - 1)]
                        _LOGGER.warning(f"Retrying request in {backoff_time} seconds... (attempt {retry_count + 1}/{API_RETRY_ATTEMPTS})")
                        await asyncio.sleep(backoff_time)
                        return await self._request(url, method, params, retry_count + 1)
                    raise EzvizCloudChinaApiError(error_msg)

                # 解析响应
                try:
                    data = await resp.json()
                except Exception as json_error:
                    error_msg = f"Failed to parse JSON response: {json_error}"
                    _LOGGER.error(error_msg)
                    raise EzvizCloudChinaApiError(error_msg)

                # 检查API错误
                if data.get("code") != "200":
                    error_msg = f"API error: {data.get('code')} - {data.get('msg')}"
                    _LOGGER.error(error_msg)

                    # 处理token失效错误，尝试刷新token
                    if data.get("code") == "10002" and url != API_GET_TOKEN:
                        _LOGGER.info("Access token expired, refreshing...")
                        # 刷新token
                        await self.get_token(force_refresh=True)
                        # 重试原请求
                        if retry_count < API_RETRY_ATTEMPTS:
                            _LOGGER.info("Retrying request with new token")
                            return await self._request(url, method, params, retry_count + 1)

                    # 其他错误，如果可重试，则重试
                    if retry_count < API_RETRY_ATTEMPTS:
                        backoff_time = self._retry_backoff[min(retry_count, len(self._retry_backoff) - 1)]
                        _LOGGER.warning(f"Retrying request in {backoff_time} seconds... (attempt {retry_count + 1}/{API_RETRY_ATTEMPTS})")
                        await asyncio.sleep(backoff_time)
                        return await self._request(url, method, params, retry_count + 1)

                    raise EzvizCloudChinaApiError(error_msg)

                return data.get("data", {})

        except asyncio.TimeoutError:
            error_msg = f"Request timed out after {API_TIMEOUT} seconds"
            _LOGGER.error(error_msg)
            # 重试超时请求
            if retry_count < API_RETRY_ATTEMPTS:
                backoff_time = self._retry_backoff[min(retry_count, len(self._retry_backoff) - 1)]
                _LOGGER.warning(f"Retrying timed out request in {backoff_time} seconds... (attempt {retry_count + 1}/{API_RETRY_ATTEMPTS})")
                await asyncio.sleep(backoff_time)
                return await self._request(url, method, params, retry_count + 1)
            raise EzvizCloudChinaApiError(error_msg)

        except aiohttp.ClientError as err:
            error_msg = f"Request error: {err}"
            _LOGGER.error(error_msg)
            # 重试网络错误
            if retry_count < API_RETRY_ATTEMPTS:
                backoff_time = self._retry_backoff[min(retry_count, len(self._retry_backoff) - 1)]
                _LOGGER.warning(f"Retrying after client error in {backoff_time} seconds... (attempt {retry_count + 1}/{API_RETRY_ATTEMPTS})")
                await asyncio.sleep(backoff_time)
                return await self._request(url, method, params, retry_count + 1)
            raise EzvizCloudChinaApiError(error_msg)

        except Exception as err:
            error_msg = f"Unexpected error: {err}"
            _LOGGER.error(error_msg)
            # 重试其他错误
            if retry_count < API_RETRY_ATTEMPTS:
                backoff_time = self._retry_backoff[min(retry_count, len(self._retry_backoff) - 1)]
                _LOGGER.warning(f"Retrying after unexpected error in {backoff_time} seconds... (attempt {retry_count + 1}/{API_RETRY_ATTEMPTS})")
                await asyncio.sleep(backoff_time)
                return await self._request(url, method, params, retry_count + 1)
            raise EzvizCloudChinaApiError(error_msg)

    async def ensure_token_valid(self) -> str:
        """Ensure the access token is valid, refreshing if needed."""
        async with self._token_lock:
            current_time = int(time.time() * 1000)  # Convert to milliseconds

            # If token is missing or will expire in the next hour, refresh it
            if (not self.access_token or
                    current_time > (self.token_expires_at - 3600000)):  # 1 hour margin
                await self.get_token()

            return self.access_token

    async def get_token(self, force_refresh=False) -> str:
        """Get a new access token."""
        async with self._token_lock:
            # 如果不是强制刷新，并且令牌有效，则直接返回
            current_time = int(time.time() * 1000)
            if not force_refresh and self.access_token and current_time < (self.token_expires_at - 3600000):
                return self.access_token

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
            "channelNo": channel_no
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
            # 使用0重试尝试次数以使用请求重试逻辑
            await self._request(API_SET_PRIVACY, "POST", params, 0)

            # 延迟一小段时间以确保命令已处理
            await asyncio.sleep(0.5)

            # 验证状态更改是否成功
            current_status = await self.get_privacy_status(device_serial, channel_no)
            expected_status = enable

            if current_status == expected_status:
                _LOGGER.debug(f"Privacy mode for {device_serial} successfully set to {enable}")
                return True
            else:
                _LOGGER.warning(f"Privacy mode state mismatch for {device_serial}: expected {enable}, got {current_status}")
                # 可能需要重试或其他处理...
                return False

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
                self.session = aiohttp.ClientSession(timeout=ClientTimeout(total=API_TIMEOUT))

            for retry in range(API_RETRY_ATTEMPTS + 1):  # +1 for initial attempt
                try:
                    async with self.session.get(url, timeout=ClientTimeout(total=API_TIMEOUT)) as resp:
                        if resp.status != 200:
                            error_text = await resp.text()
                            _LOGGER.error(f"Failed to get device capture: {error_text}")

                            # 如果不是最后一次尝试，则重试
                            if retry < API_RETRY_ATTEMPTS:
                                backoff_time = self._retry_backoff[min(retry, len(self._retry_backoff) - 1)]
                                _LOGGER.warning(f"Retrying capture in {backoff_time} seconds... (attempt {retry + 1}/{API_RETRY_ATTEMPTS})")
                                await asyncio.sleep(backoff_time)
                                continue

                            raise EzvizCloudChinaApiError(f"Failed to get device capture: {resp.status}")

                        content_type = resp.headers.get("Content-Type", "")
                        # 检查是否是图片响应
                        if "image" in content_type:
                            return await resp.read()
                        else:
                            # 可能返回了错误信息的JSON
                            error_text = await resp.text()

                            # 判断是否是token过期，如果是则刷新token并重试
                            if "10002" in error_text and retry < API_RETRY_ATTEMPTS:
                                _LOGGER.info("Token expired during capture request, refreshing...")
                                await self.get_token(force_refresh=True)
                                url = f"{API_GET_DEVICE_CAPTURE}?accessToken={self.access_token}&deviceSerial={device_serial}&channelNo={channel_no}"
                                continue

                            _LOGGER.error(f"Expected image but got: {error_text}")

                            # 如果不是最后一次尝试，则重试
                            if retry < API_RETRY_ATTEMPTS:
                                backoff_time = self._retry_backoff[min(retry, len(self._retry_backoff) - 1)]
                                _LOGGER.warning(f"Retrying capture in {backoff_time} seconds... (attempt {retry + 1}/{API_RETRY_ATTEMPTS})")
                                await asyncio.sleep(backoff_time)
                                continue

                            raise EzvizCloudChinaApiError(f"Invalid capture response: {error_text}")

                except (asyncio.TimeoutError, aiohttp.ClientError) as err:
                    if retry < API_RETRY_ATTEMPTS:
                        backoff_time = self._retry_backoff[min(retry, len(self._retry_backoff) - 1)]
                        _LOGGER.warning(f"Capture request error, retrying in {backoff_time} seconds... (attempt {retry + 1}/{API_RETRY_ATTEMPTS}): {err}")
                        await asyncio.sleep(backoff_time)
                    else:
                        _LOGGER.error(f"Failed to get device capture after {API_RETRY_ATTEMPTS} attempts: {err}")
                        raise EzvizCloudChinaApiError(f"Failed to get device capture: {err}")

            # 如果所有重试都失败
            raise EzvizCloudChinaApiError(f"Failed to get device capture after {API_RETRY_ATTEMPTS} attempts")

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