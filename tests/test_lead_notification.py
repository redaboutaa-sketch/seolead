"""Le routage des leads : un lead capturé doit atteindre un humain.

L'échec métier que cette couche empêche : des leads en base, personne de
prévenu, personne ne rappelle. Les invariants épinglés ici :

- la destination est la CONFIGURATION (`organization.lead_destination_email`,
  fournie par le propriétaire) — jamais une adresse codée en dur ;
- un échec de notification ne coûte JAMAIS le lead : capture 201, base
  intacte, log bruyant ;
- sans transport SMTP, le repli est honnête : il ne prétend pas livrer, il
  prévient dans les logs ;
- la destination ne voyage pas dans le DTO public du site.
"""
from __future__ import annotations

import pytest

from app.site.config import load_site
from app.site.lead_notification import (LeadNotification, LogOnlyLeadNotifier,
                                        build_notification, notify_lead)


class _RecordingNotifier:
    def __init__(self, fail: bool = False):
        self.sent: list[LeadNotification] = []
        self._fail = fail

    async def send(self, notification: LeadNotification) -> bool:
        if self._fail:
            raise RuntimeError("smtp down")
        self.sent.append(notification)
        return True


class _Lead:
    """Le sous-ensemble de CapturedLead que la notification lit."""

    id = "00000000-0000-0000-0000-000000000001"
    conversion_type = "ESTIMATE_REQUEST"
    language = "fr"
    first_name = "Ada"
    last_name = "L."
    email = "ada@example.org"
    phone = "+32470000000"
    postcode = "1000"
    qualification = {"project_timeframe": "ASAP", "financing_interest": "YES",
                     "appointment_interest": "YES", "battery_interest": "YES"}


class TestDestinationIsConfiguration:
    def test_the_destination_is_the_configured_value_not_a_constant(self):
        config = load_site("solar_be")
        notification = build_notification(_Lead(), config)
        assert notification is not None
        assert notification.to == config.organization.lead_destination_email
        # La preuve demandée : destination == valeur de configuration,
        # pas une chaîne codée quelque part.
        assert config.organization.lead_destination_email \
            == "reda.boutaa.seolead@gmail.com"

    def test_without_a_destination_nothing_is_built_and_it_is_loud(self, caplog):
        config = load_site("solar_be").model_copy(deep=True)
        config.organization.lead_destination_email = None
        with caplog.at_level("WARNING"):
            assert build_notification(_Lead(), config) is None
        assert any("nobody notified" in r.message for r in caplog.records)

    def test_the_body_carries_what_an_operator_needs_and_no_more(self):
        config = load_site("solar_be")
        notification = build_notification(_Lead(), config)
        body = notification.body
        assert "ada@example.org" in body and "+32470000000" in body
        assert "ASAP" in body and "YES" in body
        # Minimisation : ni consentements, ni attribution, ni dump complet.
        for absent in ("consent", "utm_", "referrer", "granted"):
            assert absent not in body.lower()


class TestFailureNeverCostsTheLead:
    @pytest.mark.asyncio
    async def test_a_transport_failure_is_FAILED_and_raises_nothing(self,
                                                                    caplog):
        config = load_site("solar_be")
        with caplog.at_level("ERROR"):
            outcome = await notify_lead(_Lead(), config,
                                        notifier=_RecordingNotifier(fail=True))
        assert outcome == "FAILED"
        assert any("lead is stored" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_the_recording_transport_receives_the_configured_to(self):
        config = load_site("solar_be")
        notifier = _RecordingNotifier()
        assert await notify_lead(_Lead(), config, notifier=notifier) == "SENT"
        assert [n.to for n in notifier.sent] \
            == [config.organization.lead_destination_email]

    @pytest.mark.asyncio
    async def test_every_outcome_is_a_queryable_state(self):
        """« Aucun lead oublié » vit dans ces états, pas dans un grep : sans
        destination → NO_DESTINATION ; repli sans transport → NO_TRANSPORT."""
        config = load_site("solar_be").model_copy(deep=True)
        config.organization.lead_destination_email = None
        assert await notify_lead(_Lead(), config,
                                 notifier=_RecordingNotifier()) \
            == "NO_DESTINATION"
        assert await notify_lead(_Lead(), load_site("solar_be"),
                                 notifier=LogOnlyLeadNotifier()) \
            == "NO_TRANSPORT"

    @pytest.mark.asyncio
    async def test_the_log_only_fallback_does_not_pretend(self, caplog):
        with caplog.at_level("WARNING"):
            delivered = await LogOnlyLeadNotifier().send(LeadNotification(
                to="x@example.org", subject="s", body="b"))
        assert delivered is False
        assert any("NOT delivered" in r.message for r in caplog.records)


class _StubSmtp:
    """smtplib.SMTP factice — enregistre ce que le transport ferait."""

    instances: list["_StubSmtp"] = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port = host, port
        self.started_tls = False
        self.login_args = None
        self.messages = []
        _StubSmtp.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.login_args = (username, password)

    def send_message(self, message):
        self.messages.append(message)


class TestSmtpTransport:
    @pytest.mark.asyncio
    async def test_the_relay_receives_starttls_auth_and_the_message(self,
                                                                    monkeypatch):
        from app.site import lead_notification as ln
        monkeypatch.setattr(ln.smtplib, "SMTP", _StubSmtp)
        _StubSmtp.instances.clear()
        notifier = ln.SmtpLeadNotifier(
            host="smtp-relay.brevo.com", port=587,
            username="login@smtp-brevo.com", password="secret",
            sender="expediteur.verifie@example.org", starttls=True)
        assert await notifier.send(LeadNotification(
            to="dest@example.org", subject="s", body="b")) is True
        smtp = _StubSmtp.instances[0]
        assert (smtp.host, smtp.port) == ("smtp-relay.brevo.com", 587)
        assert smtp.started_tls is True
        assert smtp.login_args == ("login@smtp-brevo.com", "secret")
        assert smtp.messages[0]["To"] == "dest@example.org"
        assert smtp.messages[0]["From"] == "expediteur.verifie@example.org"

    @pytest.mark.asyncio
    async def test_without_a_sender_the_from_is_the_destination(self,
                                                                monkeypatch):
        # Un LOGIN SMTP n'est pas une identité d'expéditeur ; sans
        # SEOLEAD_SMTP_SENDER, l'opérateur s'écrit depuis sa propre adresse.
        from app.site import lead_notification as ln
        monkeypatch.setattr(ln.smtplib, "SMTP", _StubSmtp)
        _StubSmtp.instances.clear()
        notifier = ln.SmtpLeadNotifier(
            host="smtp-relay.brevo.com", port=587,
            username="login@smtp-brevo.com", password="secret",
            sender="", starttls=True)
        await notifier.send(LeadNotification(
            to="dest@example.org", subject="s", body="b"))
        assert _StubSmtp.instances[0].messages[0]["From"] == "dest@example.org"


def test_both_env_spellings_configure_the_transport(monkeypatch):
    # L'ordre de mise en production a fourni SEOLEAD_SMTP_USER ; le code
    # acceptait SEOLEAD_SMTP_USERNAME. Les deux graphies doivent porter.
    from app.core.config import Settings
    monkeypatch.setenv("SEOLEAD_SMTP_HOST", "smtp-relay.brevo.com")
    monkeypatch.setenv("SEOLEAD_SMTP_USER", "court@smtp-brevo.com")
    settings = Settings(_env_file=None)
    assert settings.smtp_configured is True
    assert settings.smtp_username == "court@smtp-brevo.com"
    monkeypatch.delenv("SEOLEAD_SMTP_USER")
    monkeypatch.setenv("SEOLEAD_SMTP_USERNAME", "long@smtp-brevo.com")
    assert Settings(_env_file=None).smtp_username == "long@smtp-brevo.com"


# La preuve que le DTO public ne transporte pas la destination de routage
# vit dans tests/test_site_api.py, avec la fixture client de ce module.
