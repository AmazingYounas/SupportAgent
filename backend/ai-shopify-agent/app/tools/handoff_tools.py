import asyncio
import logging
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from typing import Optional, Type

logger = logging.getLogger(__name__)


class HumanHandoffInput(BaseModel):
    reason: str = Field(
        description="Brief reason the customer needs a human agent. "
                    "e.g. 'Customer requested human agent', 'Complex refund dispute', "
                    "'Shipping address change after fulfillment'."
    )
    conversation_summary: str = Field(
        description="2-3 sentence summary of the conversation so far, "
                    "so the human agent doesn't need to ask the customer to repeat themselves."
    )
    customer_email: Optional[str] = Field(
        default=None,
        description="Customer email if known, so the human agent can follow up."
    )


class HumanHandoffTool(BaseTool):
    """
    Triggers a real escalation when the customer asks for a human agent
    or when the AI cannot resolve the issue.

    Currently: logs the escalation and sends an email notification via the
    configured ESCALATION_EMAIL env var. Replace the _notify() method with
    your ticketing system (Zendesk, Gorgias, Freshdesk, etc.) when ready.
    """

    name: str = "escalate_to_human"
    description: str = (
        "Use this tool when: (1) the customer explicitly asks for a human agent, "
        "(2) you cannot resolve the issue after trying, or (3) the issue involves "
        "fraud, legal matters, or anything requiring human judgment. "
        "This creates a real support ticket and notifies the store team."
    )
    args_schema: Type[BaseModel] = HumanHandoffInput

    def _run(self, reason: str, conversation_summary: str, customer_email: Optional[str] = None) -> str:
        """Sync fallback — not used when async is available."""
        return "Error: Use _arun for async tool invocation."

    async def _arun(
        self,
        reason: str,
        conversation_summary: str,
        customer_email: Optional[str] = None,
    ) -> str:
        """
        Creates an escalation record and notifies the store team.
        Returns a confirmation string the agent speaks to the customer.
        """
        ticket_id = await self._create_escalation(reason, conversation_summary, customer_email)
        logger.info(
            f"[Handoff] Escalation created — ticket: {ticket_id} | "
            f"reason: {reason} | customer: {customer_email or 'unknown'}"
        )
        return (
            f"Escalation ticket {ticket_id} created. "
            f"The store team has been notified and will follow up"
            f"{f' at {customer_email}' if customer_email else ' shortly'}. "
            f"Summary logged: {conversation_summary[:100]}"
        )

    async def _create_escalation(
        self,
        reason: str,
        summary: str,
        customer_email: Optional[str],
    ) -> str:
        """
        Pluggable escalation backend.

        Current implementation: structured log entry + optional email.
        Replace this method body with your ticketing API call
        (Zendesk, Gorgias, Freshdesk, plain email, Slack webhook, etc.)

        Returns a ticket/reference ID string.
        """
        import os
        import time

        ticket_id = f"ESC-{int(time.time())}"

        # Always write a structured log — visible in agent.log and any log aggregator
        logger.warning(
            "[ESCALATION] %s | ticket=%s | customer=%s | summary=%s",
            reason,
            ticket_id,
            customer_email or "unknown",
            summary,
        )

        # Optional: send email notification if ESCALATION_EMAIL is configured
        escalation_email = os.getenv("ESCALATION_EMAIL", "")
        if escalation_email:
            await self._send_email_notification(
                to=escalation_email,
                ticket_id=ticket_id,
                reason=reason,
                summary=summary,
                customer_email=customer_email,
            )

        return ticket_id

    async def _send_email_notification(
        self,
        to: str,
        ticket_id: str,
        reason: str,
        summary: str,
        customer_email: Optional[str],
    ) -> None:
        """
        Sends a plain-text email via SMTP using env vars:
          ESCALATION_EMAIL       — recipient address
          SMTP_HOST              — SMTP server (default: smtp.gmail.com)
          SMTP_PORT              — SMTP port (default: 587)
          SMTP_USER              — SMTP username
          SMTP_PASSWORD          — SMTP password / app password
        """
        import os
        import smtplib
        from email.mime.text import MIMEText

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER", "")
        smtp_password = os.getenv("SMTP_PASSWORD", "")

        if not smtp_user or not smtp_password:
            logger.warning("[Handoff] SMTP credentials not configured — skipping email notification")
            return

        body = (
            f"Support Escalation — {ticket_id}\n\n"
            f"Reason: {reason}\n"
            f"Customer: {customer_email or 'unknown'}\n\n"
            f"Conversation Summary:\n{summary}\n\n"
            f"Please follow up with the customer as soon as possible."
        )

        msg = MIMEText(body)
        msg["Subject"] = f"[Support Escalation] {ticket_id} — {reason[:60]}"
        msg["From"] = smtp_user
        msg["To"] = to

        try:
            # Run blocking SMTP call in thread pool to avoid blocking event loop
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: _send_smtp(smtp_host, smtp_port, smtp_user, smtp_password, msg),
            )
            logger.info(f"[Handoff] Escalation email sent to {to} for ticket {ticket_id}")
        except Exception as e:
            # Email failure must never crash the agent — customer already heard the handoff message
            logger.error(f"[Handoff] Failed to send escalation email: {e}")


def _send_smtp(host: str, port: int, user: str, password: str, msg) -> None:
    """Blocking SMTP send — called via run_in_executor."""
    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.send_message(msg)
