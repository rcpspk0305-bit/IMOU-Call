import time
import uuid
import hashlib
import logging
import requests
from typing import Optional, Tuple, Dict, Any
from app.config import Config

logger = logging.getLogger(__name__)

class ImouService:
    """
    Service client for interacting with the Imou Open API (easy4ip).
    Handles token authentication and device status queries.
    """
    def __init__(self, config: type = Config):
        self.config = config
        self._cached_token: Optional[str] = None
        self._token_expires_at: float = 0

    def _generate_signature(self, system_time: int, nonce: str, app_secret: str) -> str:
        """
        Generates MD5 signature for Imou Open API requests.
        Format: md5("time:{time},nonce:{nonce},appSecret:{appSecret}")
        """
        raw_str = f"time:{system_time},nonce:{nonce},appSecret:{app_secret}"
        return hashlib.md5(raw_str.encode("utf-8")).hexdigest()

    def get_access_token(self, force_refresh: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetches an open API accessToken from https://openapi.easy4ip.com/openapi/accessToken.
        Uses cached token if valid and not expired.

        :return: Tuple of (accessToken, error_message)
        """
        now = time.time()
        if not force_refresh and self._cached_token and now < self._token_expires_at:
            logger.debug("Using cached Imou access token")
            return self._cached_token, None

        url = f"{self.config.IMOU_API_BASE_URL.rstrip('/')}/accessToken"
        system_time = int(now)
        nonce = uuid.uuid4().hex[:16]
        sign = self._generate_signature(system_time, nonce, self.config.IMOU_APP_SECRET)

        payload = {
            "system": {
                "ver": "1.1",
                "sign": sign,
                "appId": self.config.IMOU_APP_ID,
                "time": system_time,
                "nonce": nonce
            },
            "params": {
                "appId": self.config.IMOU_APP_ID,
                "appSecret": self.config.IMOU_APP_SECRET
            },
            "id": str(int(now))
        }

        logger.info("Fetching new Imou access token from %s", url)
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                err_msg = f"HTTP Error {response.status_code}: {response.text}"
                logger.error("Failed to fetch Imou access token: %s", err_msg)
                return None, err_msg

            data = response.json()
            # Parse result data according to Imou OpenAPI standard JSON-RPC format
            result = data.get("result", {})
            result_data = result.get("data", {})
            
            access_token = (
                result_data.get("accessToken") or
                result.get("accessToken") or
                data.get("accessToken")
            )

            if not access_token:
                err_msg = f"No accessToken in Imou response: {data}"
                logger.error(err_msg)
                return None, err_msg

            # Cache token (default expire 7 days or 3600s if provided)
            expire_seconds = int(result_data.get("expireTime", 3600))
            self._cached_token = access_token
            self._token_expires_at = now + expire_seconds - 60  # 60s safety buffer
            logger.info("Successfully obtained Imou access token")
            return access_token, None

        except requests.RequestException as e:
            err_msg = f"Network exception while requesting access token: {str(e)}"
            logger.exception(err_msg)
            return None, err_msg

    def get_device_online_status(self, device_id: str, access_token: Optional[str] = None) -> Tuple[Optional[bool], Optional[str]]:
        """
        Queries the device online status via Imou API (deviceOnline or listDeviceOnline endpoint).

        :param device_id: The Imou camera Device ID / Serial Number.
        :param access_token: Optional token, fetched automatically if not provided.
        :return: Tuple of (is_online: bool | None, error_message: str | None)
                 is_online is True if camera is online, False if offline, None if request failed.
        """
        if not access_token:
            token, err = self.get_access_token()
            if err or not token:
                return None, f"Could not obtain access token: {err}"
            access_token = token

        url = f"{self.config.IMOU_API_BASE_URL.rstrip('/')}/deviceOnline"
        system_time = int(time.time())
        nonce = uuid.uuid4().hex[:16]
        sign = self._generate_signature(system_time, nonce, self.config.IMOU_APP_SECRET)

        payload = {
            "system": {
                "ver": "1.1",
                "sign": sign,
                "appId": self.config.IMOU_APP_ID,
                "time": system_time,
                "nonce": nonce
            },
            "params": {
                "token": access_token,
                "accessToken": access_token,
                "deviceId": device_id
            },
            "id": str(system_time)
        }

        logger.info("Querying Imou device online status for device '%s'", device_id)
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                err_msg = f"HTTP Error {response.status_code}: {response.text}"
                logger.error("Failed to query device online status: %s", err_msg)
                return None, err_msg

            data = response.json()
            result = data.get("result", {})
            result_data = result.get("data", {})

            # Check online status in response (can be onLine, status, channels, etc.)
            raw_status = (
                result_data.get("onLine") or
                result_data.get("status") or
                result.get("onLine") or
                data.get("onLine")
            )

            # Support list channel response
            if raw_status is None and "channels" in result_data and len(result_data["channels"]) > 0:
                raw_status = result_data["channels"][0].get("onLine")

            if raw_status is None:
                err_msg = f"Could not parse online status from Imou response: {data}"
                logger.error(err_msg)
                return None, err_msg

            status_str = str(raw_status).strip().lower()
            is_online = status_str in ("1", "true", "online", "on")
            
            logger.info("Device '%s' online status: %s (raw: %s)", device_id, "ONLINE" if is_online else "OFFLINE", raw_status)
            return is_online, None

        except requests.RequestException as e:
            err_msg = f"Network exception while querying device online status: {str(e)}"
            logger.exception(err_msg)
            return None, err_msg

# Global service instance
imou_service = ImouService()
