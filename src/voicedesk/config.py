"""Runtime settings. Telephony & optional LLM integrations default to disabled."""
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    db_path: Path = Path("data/voicedesk.sqlite")
    business_name: str = "Northstar Demo Studio"
    timezone: str = "America/New_York"
    operator_key: str = ""
    demo_mode: bool = True
    twilio_auth_token: str = ""
    public_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"

    @classmethod
    def from_env(cls):
        get = os.environ.get
        return cls(
            db_path=Path(get("VD_DB_PATH", "data/voicedesk.sqlite")),
            business_name=get("VD_BUSINESS_NAME", "Northstar Demo Studio"),
            timezone=get("VD_TIMEZONE", "America/New_York"),
            operator_key=get("VD_OPERATOR_KEY", ""),
            demo_mode=get("VD_DEMO_MODE", "true").lower() == "true",
            twilio_auth_token=get("VD_TWILIO_AUTH_TOKEN", ""),
            public_base_url=get("VD_PUBLIC_BASE_URL", ""),
            openai_api_key=get("VD_OPENAI_API_KEY", ""),
            openai_model=get("VD_OPENAI_MODEL", "gpt-4.1-mini"),
        )

    def validate(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Invalid IANA business timezone") from exc
        if not self.business_name or len(self.business_name) > 100:
            raise ValueError("Business name must have 1 to 100 characters")
        if self.public_base_url:
            parsed = urlsplit(self.public_base_url)
            if (parsed.scheme != "https" or not parsed.netloc
                or parsed.username or parsed.password or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
                raise ValueError("VD_PUBLIC_BASE_URL must be a bare public HTTPS origin")
        if self.twilio_auth_token and len(self.twilio_auth_token) < 16:
            raise ValueError("Invalid Twilio token length")

    @property
    def operator_ready(self):
        return len(self.operator_key) >= 24 and not self.operator_key.startswith("REPLACE_")

    @property
    def telephony_ready(self):
        return (len(self.twilio_auth_token) >= 16 and bool(self.public_base_url))
