import time
import uuid
import hashlib
import logging
import random
import requests
from typing import Optional, Tuple, Dict, Any
from app.config import Config

logger = logging.getLogger(__name__)

def _execute_with_retry(operation_func, max_attempts=3, base_delay=1.0, max_delay=10.0):
    """
    Executes an Imou HTTP API operation function with exponential backoff retries.
    If all attempts fail, it raises the last exception so the caller can handle it.
    """
    attempt = 1
    delay = base_delay
    while True:
        try:
            return operation_func()
        except Exception as e:
            if attempt >= max_attempts:
                logger.error("Imou API call failed after %d consecutive attempts. Error: %s", attempt, str(e))
                raise e
            
            jitter = random.uniform(0, 0.1 * delay)
            sleep_time = min(delay + jitter, max_delay)
            logger.warning("Imou API attempt %d failed: %s. Retrying in %.2f seconds...", attempt, str(e), sleep_time)
            time.sleep(sleep_time)
            attempt += 1
            delay *= 2

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
        clean_secret = str(app_secret).strip()
        raw_str = f"time:{system_time},nonce:{nonce},appSecret:{clean_secret}"
        return hashlib.md5(raw_str.encode("utf-8")).hexdigest().lower()

    def get_access_token(self, force_refresh: bool = False) -> Tuple[Optional[str], Optional[str]]:
        """
        Fetches an open API accessToken from https://openapi.easy4ip.com/openapi/accessToken.
        Uses cached token if valid and not expired.

        :return: Tuple of (accessToken, error_message)
        """
        now = time.time()
        # EXPIRY-BASED TOKEN CACHING: Store the Imou accessToken in local memory with its exact expiration timestamp
        if not force_refresh and self._cached_token and now < self._token_expires_at:
            logger.debug("Using cached Imou access token. Expires in %d seconds", int(self._token_expires_at - now))
            return self._cached_token, None

        url = f"{self.config.IMOU_API_BASE_URL.rstrip('/')}/accessToken"
        current_time = int(now)
        import string
        random_nonce = "".join(random.choices(string.ascii_letters + string.digits, k=32))
        app_secret = str(self.config.IMOU_APP_SECRET).strip()
        app_id = str(self.config.IMOU_APP_ID).strip()
        random_uuid_str = str(uuid.uuid4())

        sign_string = f"time:{current_time},nonce:{random_nonce},appSecret:{app_secret}"
        computed_sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()

        payload = {
            "system": {
                "ver": "1.0",
                "appId": app_id,
                "sign": computed_sign,
                "time": int(current_time),
                "nonce": random_nonce
            },
            "id": random_uuid_str,
            "params": {}
        }

        logger.info("Fetching new Imou access token from %s", url)
        try:
            def op():
                return requests.post(url, json=payload, timeout=10)
            response = _execute_with_retry(op)
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

            # Cache token with its exact expiration timestamp (default: 3600 seconds if not provided)
            expire_seconds = int(result_data.get("expireTime", 3600))
            self._cached_token = access_token
            # Subtract 60 seconds as a safe buffer window
            self._token_expires_at = now + expire_seconds - 60
            logger.info("Successfully obtained Imou access token. Cache set to expire in %d seconds.", expire_seconds)
            return access_token, None

        except Exception as e:
            err_msg = f"Exception while requesting access token: {str(e)}"
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
        import string
        nonce = "".join(random.choices(string.ascii_letters + string.digits, k=32))
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
            def op():
                return requests.post(url, json=payload, timeout=10)
            response = _execute_with_retry(op)
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

        except Exception as e:
            err_msg = f"Exception while querying device online status: {str(e)}"
            logger.exception(err_msg)
            return None, err_msg

# Global service instance
imou_service = ImouService()

