from __future__ import annotations

import asyncio
import json
import smtplib
import ssl
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import parseaddr
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from app.tools.errors import ToolFailure, ToolPolicyViolation
from app.tools.subscription import SubscriptionProvider


class SendDigestArguments(BaseModel):
    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    subject: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=200_000)


@dataclass(frozen=True, slots=True)
class SMTPConfig:
    enabled: bool = False
    host: str = ""
    port: int = 587
    username: str = ""
    password: str = ""
    from_address: str = ""
    use_tls: bool = True


class DigestDeliveryTool:
    def __init__(
        self,
        *,
        subscriptions: SubscriptionProvider,
        outbox_dir: Path,
        smtp: SMTPConfig | None = None,
    ) -> None:
        self._subscriptions = subscriptions
        self._outbox_dir = outbox_dir.resolve()
        self._smtp = smtp or SMTPConfig()

    async def send_digest(self, arguments: SendDigestArguments) -> dict[str, object]:
        if any(character in arguments.subject for character in "\r\n"):
            raise ToolPolicyViolation("invalid_subject", "Digest subject contains a newline")
        profile = await self._subscriptions.get(arguments.user_id)
        if profile is None:
            raise ToolFailure(
                "subscription_not_found",
                f"No subscription exists for user: {arguments.user_id}",
            )
        recipient = self._validated_email(profile.email, "subscription email")

        if not self._smtp.enabled:
            return await asyncio.to_thread(self._write_outbox, arguments, recipient)

        sender = self._validated_email(self._smtp.from_address, "SMTP sender")
        if not self._smtp.host:
            raise ToolFailure("smtp_not_configured", "SMTP_HOST must be configured")
        await asyncio.to_thread(self._send_smtp, arguments, recipient, sender)
        return {"mode": "smtp", "recipient": recipient, "delivered": True}

    def _write_outbox(
        self,
        arguments: SendDigestArguments,
        recipient: str,
    ) -> dict[str, object]:
        self._outbox_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}-{uuid4().hex}.json"
        path = self._outbox_dir / filename
        payload = {
            "user_id": arguments.user_id,
            "recipient": recipient,
            "subject": arguments.subject,
            "content": arguments.content,
            "created_at": datetime.now(UTC).isoformat(),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {
            "mode": "outbox",
            "recipient": recipient,
            "delivered": False,
            "path": f"outbox/{filename}",
        }

    def _send_smtp(
        self,
        arguments: SendDigestArguments,
        recipient: str,
        sender: str,
    ) -> None:
        message = EmailMessage()
        message["Subject"] = arguments.subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(arguments.content)

        try:
            with smtplib.SMTP(self._smtp.host, self._smtp.port, timeout=15) as client:
                if self._smtp.use_tls:
                    client.starttls(context=ssl.create_default_context())
                if self._smtp.username:
                    client.login(self._smtp.username, self._smtp.password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise ToolFailure("smtp_delivery_failed", f"SMTP delivery failed: {exc}") from exc

    @staticmethod
    def _validated_email(value: str, label: str) -> str:
        display_name, address = parseaddr(value)
        if (
            display_name
            or address != value
            or "@" not in address
            or any(character in value for character in "\r\n")
        ):
            raise ToolPolicyViolation("invalid_email", f"Invalid {label}")
        return address
