"""Lead notification: a captured lead must reach a human.

The business failure this file prevents is silent accumulation — leads stored,
nobody told, nobody calls back. The capture path (`lead_capture`) stores and
attributes; THIS layer tells the operator, after commit, and its failure can
never cost the lead: a notification error is logged loudly and the API answer
stays 201, because the lead is already safe in the database.

The destination is CONFIGURATION — `organization.lead_destination_email` in
the site's YAML, owner-supplied — never a hardcoded address. The transport is
environment — SMTP settings in `.env` — never the repository. Both unset are
first-class states: no destination means the site has nowhere to notify (a
loud log, so the gap is visible), no transport means the operator has not
supplied SMTP credentials yet (same loudness, and the runbook names it).

The notification body is deliberately minimal: identifiers and the answers an
operator needs to act (who to call, about what, when). It carries no consent
texts, no attribution trail, no qualification dump — the database holds those,
and an email is a copy that leaves the system.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

from app.core.config import get_settings
from app.models import CapturedLead
from app.site.config import SiteConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LeadNotification:
    """What the operator is told. Built once, sent by whatever transport."""

    to: str
    subject: str
    body: str


class LeadNotifier(Protocol):
    async def send(self, notification: LeadNotification) -> bool: ...


class SmtpLeadNotifier:
    """Sends through the SMTP relay named in the environment.

    Synchronous smtplib in a thread: one message per lead, no pool needed.
    """

    def __init__(self, *, host: str, port: int, username: str, password: str,
                 sender: str, starttls: bool = True) -> None:
        self._host, self._port = host, port
        self._username, self._password = username, password
        self._sender, self._starttls = sender, starttls

    async def send(self, notification: LeadNotification) -> bool:
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = notification.to
        message["Subject"] = notification.subject
        message.set_content(notification.body)

        def _deliver() -> None:
            with smtplib.SMTP(self._host, self._port, timeout=20) as smtp:
                if self._starttls:
                    smtp.starttls()
                if self._username:
                    smtp.login(self._username, self._password)
                smtp.send_message(message)

        await asyncio.to_thread(_deliver)
        return True


class LogOnlyLeadNotifier:
    """The honest fallback when no SMTP transport is configured.

    It does NOT pretend to deliver: it logs at WARNING with the lead id and
    the configured destination, so every uncontacted lead is visible in the
    operator's logs until the transport credentials arrive.
    """

    async def send(self, notification: LeadNotification) -> bool:
        logger.warning(
            "lead notification NOT delivered - SMTP transport not configured",
            extra={"destination": notification.to,
                   "subject": notification.subject})
        return False


def build_notification(lead: CapturedLead, config: SiteConfig
                       ) -> LeadNotification | None:
    """The message for THIS lead, addressed to the CONFIGURED destination.

    Returns None — loudly — when the configuration carries no destination:
    a site without a lead destination is a site whose leads reach nobody,
    and that must be visible, not silent.
    """
    destination = (config.organization.lead_destination_email or "").strip()
    if not destination:
        logger.warning(
            "no lead_destination_email configured - lead stored, nobody notified",
            extra={"lead_id": str(lead.id), "site": config.site_id})
        return None

    qualification = lead.qualification or {}
    lines = [
        f"Nouvelle demande sur {config.brand_name} ({config.site_id}).",
        "",
        f"Lead : {lead.id}",
        f"Type : {lead.conversion_type} · Langue : {lead.language}",
        f"Nom : {' '.join(v for v in (lead.first_name, lead.last_name) if v) or '—'}",
        f"Email : {lead.email}",
        f"Téléphone : {lead.phone or '—'}",
        f"Code postal : {lead.postcode or '—'}",
        "",
        f"Échéance : {qualification.get('project_timeframe', '—')}",
        f"Intérêt solution sans achat immédiat : "
        f"{qualification.get('financing_interest', '—')}",
        f"Intérêt rendez-vous : {qualification.get('appointment_interest', '—')}",
        f"Batterie : {qualification.get('battery_interest', '—')}",
        "",
        f"Dossier complet : en base, lead {lead.id}.",
        "Cet email est une notification, pas le dossier.",
    ]
    return LeadNotification(
        to=destination,
        subject=f"[{config.brand_name}] Nouvelle demande — "
                f"{lead.postcode or 'BE'} — {lead.conversion_type}",
        body="\n".join(lines),
    )


def default_notifier() -> LeadNotifier:
    """SMTP when the environment supplies it, the loud no-op otherwise."""
    settings = get_settings()
    if settings.smtp_configured:
        return SmtpLeadNotifier(
            host=settings.smtp_host, port=settings.smtp_port,
            username=settings.smtp_username, password=settings.smtp_password,
            sender=settings.smtp_sender or settings.smtp_username,
            starttls=settings.smtp_starttls)
    return LogOnlyLeadNotifier()


async def notify_lead(lead: CapturedLead, config: SiteConfig,
                      notifier: LeadNotifier | None = None) -> bool:
    """Best-effort, after commit. Never raises: the lead is already stored,
    and no notification failure may turn a captured lead into an error."""
    try:
        notification = build_notification(lead, config)
        if notification is None:
            return False
        delivered = await (notifier or default_notifier()).send(notification)
        if delivered:
            logger.info("lead notification delivered",
                        extra={"lead_id": str(lead.id),
                               "destination": notification.to})
        return delivered
    except Exception:
        logger.exception("lead notification failed - lead is stored, "
                         "follow up manually", extra={"lead_id": str(lead.id)})
        return False
