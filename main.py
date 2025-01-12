import requests
from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, List


class Priority(Enum):
    LOWEST = -2  # No notification/alert
    LOW = -1  # No sound/vibration
    NORMAL = 0  # Default priority
    HIGH = 1  # High priority, bypasses quiet hours
    EMERGENCY = 2  # Requires confirmation


@dataclass
class GlancesData:
    """Container for Glances data fields"""
    title: Optional[str] = None  # 100 chars max - description of the data
    text: Optional[str] = None  # 100 chars max - main line of data
    subtext: Optional[str] = None  # 100 chars max - second line of data
    count: Optional[int] = None  # integer (can be negative) - for simple counts
    percent: Optional[int] = None  # 0-100 - shown as progress bar/circle

    def validate(self):
        """Validate glances data fields"""
        if self.title and len(self.title) > 100:
            raise ValueError("title must be 100 characters or less")
        if self.text and len(self.text) > 100:
            raise ValueError("text must be 100 characters or less")
        if self.subtext and len(self.subtext) > 100:
            raise ValueError("subtext must be 100 characters or less")
        if self.percent is not None and not (0 <= self.percent <= 100):
            raise ValueError("percent must be between 0 and 100")

    def to_dict(self) -> Dict:
        """Convert to dictionary for API request"""
        data = {}
        if self.title is not None: data["title"] = self.title
        if self.text is not None: data["text"] = self.text
        if self.subtext is not None: data["subtext"] = self.subtext
        if self.count is not None: data["count"] = self.count
        if self.percent is not None: data["percent"] = self.percent
        return data


class PushoverError(Exception):
    """Custom exception for Pushover API errors"""
    pass


@dataclass
class PushoverResponse:
    """Container for Pushover API responses"""
    status: int
    request_id: str
    receipt: Optional[str] = None
    errors: Optional[List[str]] = None


class Pushover:
    """Main class for interacting with the Pushover API"""
    BASE_URL = "https://api.pushover.net/1"

    def __init__(self, app_token: str):
        """
        Initialize Pushover client

        Args:
            app_token: Your application's API token
        """
        self.app_token = app_token

    def send_message(
            self,
            user_key: str,
            message: str,
            title: Optional[str] = None,
            device: Optional[str] = None,
            priority: Priority = Priority.NORMAL,
            sound: Optional[str] = None,
            url: Optional[str] = None,
            url_title: Optional[str] = None,
            timestamp: Optional[int] = None,
            html: bool = False,
            monospace: bool = False,
            ttl: Optional[int] = None,
            retry: Optional[int] = None,
            expire: Optional[int] = None,
            callback_url: Optional[str] = None,
            attachment: Optional[str] = None,
    ) -> PushoverResponse:
        """
        Send a message to a user or group

        Args:
            user_key: The user/group key (or comma-separated list of user keys)
            message: The message body
            title: Message title (defaults to app name)
            device: Target specific device(s)
            priority: Message priority (from Priority enum)
            sound: Override user's default sound
            url: Supplementary URL
            url_title: Title for the URL
            timestamp: Unix timestamp of your message
            html: Enable HTML formatting
            monospace: Enable monospace formatting
            ttl: Message time to live in seconds
            retry: How often (in seconds) to retry emergency priority messages
            expire: How long (in seconds) emergency priority messages continue retrying
            callback_url: URL for emergency priority message acknowledgement
            attachment: Path to image file to attach

        Returns:
            PushoverResponse object containing status and request details

        Raises:
            PushoverError: If the API request fails
        """
        # Build payload
        payload = {
            "token": self.app_token,
            "user": user_key,
            "message": message,
            "priority": priority.value
        }

        # Add optional parameters
        if title: payload["title"] = title
        if device: payload["device"] = device
        if sound: payload["sound"] = sound
        if url: payload["url"] = url
        if url_title: payload["url_title"] = url_title
        if timestamp: payload["timestamp"] = timestamp
        if html: payload["html"] = 1
        if monospace: payload["monospace"] = 1
        if ttl: payload["ttl"] = ttl

        # Add emergency priority parameters
        if priority == Priority.EMERGENCY:
            if not retry or not expire:
                raise ValueError("Emergency priority requires retry and expire parameters")
            if retry < 30:
                raise ValueError("retry must be at least 30 seconds")
            if expire > 10800:
                raise ValueError("expire must be at most 10800 seconds (3 hours)")

            payload["retry"] = retry
            payload["expire"] = expire
            if callback_url:
                payload["callback"] = callback_url

        files = None
        if attachment:
            try:
                files = {
                    "attachment": ("image.jpg", open(attachment, "rb"), "image/jpeg")
                }
            except Exception as e:
                raise PushoverError(f"Failed to read attachment: {str(e)}")

        # Make the API request
        try:
            response = requests.post(
                f"{self.BASE_URL}/messages.json",
                data=payload,
                files=files
            )
            data = response.json()

            if response.status_code != 200:
                raise PushoverError(f"API request failed: {data.get('errors', ['Unknown error'])}")

            return PushoverResponse(
                status=data["status"],
                request_id=data["request"],
                receipt=data.get("receipt")
            )

        except requests.exceptions.RequestException as e:
            raise PushoverError(f"Request failed: {str(e)}")

    def validate_user(self, user_key: str, device: Optional[str] = None) -> bool:
        """
        Validate a user key and optionally a device name

        Args:
            user_key: User key to validate
            device: Optional device name to validate

        Returns:
            True if valid, False otherwise
        """
        payload = {
            "token": self.app_token,
            "user": user_key
        }
        if device:
            payload["device"] = device

        try:
            response = requests.post(
                f"{self.BASE_URL}/users/validate.json",
                data=payload
            )
            data = response.json()
            return data.get("status") == 1
        except:
            return False

    def check_receipt(self, receipt: str) -> Dict:
        """
        Check the status of an emergency priority notification

        Args:
            receipt: Receipt ID from emergency priority message

        Returns:
            Dictionary containing receipt status details

        Raises:
            PushoverError: If the API request fails
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/receipts/{receipt}.json",
                params={"token": self.app_token}
            )

            if response.status_code != 200:
                raise PushoverError("Failed to check receipt")

            return response.json()
        except requests.exceptions.RequestException as e:
            raise PushoverError(f"Request failed: {str(e)}")

    def cancel_emergency(self, receipt: str) -> bool:
        """
        Cancel an emergency priority notification

        Args:
            receipt: Receipt ID to cancel

        Returns:
            True if successful, False otherwise
        """
        try:
            response = requests.post(
                f"{self.BASE_URL}/receipts/{receipt}/cancel.json",
                data={"token": self.app_token}
            )
            return response.status_code == 200
        except:
            return False

    def get_sounds(self) -> Dict[str, str]:
        """
        Get list of available notification sounds

        Returns:
            Dictionary of sound name to description mappings

        Raises:
            PushoverError: If the API request fails
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/sounds.json",
                params={"token": self.app_token}
            )

            if response.status_code != 200:
                raise PushoverError("Failed to get sounds")

            data = response.json()
            return data.get("sounds", {})
        except requests.exceptions.RequestException as e:
            raise PushoverError(f"Request failed: {str(e)}")

    def update_glance(
            self,
            user_key: str,
            glances_data: GlancesData,
            device: Optional[str] = None
    ) -> PushoverResponse:
        """
        Update a Glances widget for a user

        Args:
            user_key: The user key to update glances for
            glances_data: GlancesData object containing the data to update
            device: Optional device name to restrict update to

        Returns:
            PushoverResponse object containing status and request details

        Raises:
            PushoverError: If the API request fails
            ValueError: If the glances data is invalid

        Note:
            Updates may take up to 10 minutes to appear on devices due to
            platform restrictions. For Apple Watch, updates should be at least
            20 minutes apart and are limited to 50 updates per day.
        """
        # Validate the glances data
        glances_data.validate()

        # Build payload
        payload = {
            "token": self.app_token,
            "user": user_key,
            **glances_data.to_dict()
        }

        if device:
            payload["device"] = device

        # Make the API request
        try:
            response = requests.post(
                f"{self.BASE_URL}/glances.json",
                data=payload
            )
            data = response.json()

            if response.status_code != 200:
                raise PushoverError(f"API request failed: {data.get('errors', ['Unknown error'])}")

            return PushoverResponse(
                status=data["status"],
                request_id=data["request"]
            )

        except requests.exceptions.RequestException as e:
            raise PushoverError(f"Request failed: {str(e)}")


# Example usage:
if __name__ == "__main__":
    # Initialize client
    push = Pushover("")
    USER_KEY = ""
    push.send_message(USER_KEY, "YMAX Distrubution Today")