"""The decoy field must be invisible to autofill, not just to people.

Found by the first real human submission. On 2026-08-30 the owner filled in the
form himself, in Chrome, and was refused: `submission rejected: honeypot field
was filled`. His browser had filled the trap for him.

The field was named `company_website`. Chrome maps the token `website` to its
URL/organisation heuristic and fills it from the saved profile; `autocomplete
="off"` was already set and Chrome ignored it, as it routinely does on a field
it believes it recognises. So the name is the signal that decides, and the name
is what these tests pin.

They read the shipped source rather than a running browser on purpose: Chrome's
autofill is browser-internal UI that Playwright cannot trigger, so a browser
test could only ever assert the field is hidden — which it already was, and
which did not save the owner.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

FORM = Path("web/components/LeadForm.tsx")
CSS = Path("web/app/globals.css")

# Tokens autofill engines match on. Chrome, Firefox and Safari all key off the
# field's name and id before anything else; this is the vocabulary they know.
AUTOFILL_TOKENS = (
    "name", "email", "mail", "phone", "tel", "mobile", "address", "addr",
    "street", "city", "town", "zip", "postal", "postcode", "country", "state",
    "province", "company", "organization", "organisation", "url", "website",
    "web", "site", "username", "user", "login", "password", "birth", "card",
    "cc", "credit", "given", "family", "surname", "firstname", "lastname",
)


def _decoy() -> dict[str, str]:
    """The attributes of the one input inside the off-screen wrapper."""
    source = FORM.read_text(encoding="utf-8")
    block = re.search(r'<div className="form-aux".*?</div>', source, re.S)
    assert block, "the off-screen wrapper is gone; this test guards nothing"
    return dict(re.findall(r'(\w+)="([^"]*)"', block.group(0)))


class TestTheNameCannotBeRecognised:
    @pytest.mark.parametrize("token", AUTOFILL_TOKENS)
    def test_the_field_name_matches_no_autofill_token(self, token):
        name = _decoy().get("name", "")
        assert name, "the decoy field has no name at all"
        assert token not in name.casefold(), (
            f"the decoy is named {name!r}, and {token!r} is a token autofill "
            f"matches on — this is exactly how `company_website` got filled")

    @pytest.mark.parametrize("token", AUTOFILL_TOKENS)
    def test_the_field_id_matches_no_autofill_token_either(self, token):
        assert token not in _decoy().get("id", "").casefold()

    def test_autocomplete_is_still_off(self):
        """Necessary and famously not sufficient. Kept for the browsers that obey."""
        assert _decoy().get("autoComplete") == "off"


class TestItIsOutOfEveryHumanPath:
    def test_it_is_hidden_from_assistive_technology(self):
        source = FORM.read_text(encoding="utf-8")
        wrapper = re.search(r'<div className="form-aux"[^>]*>', source)
        assert wrapper and 'aria-hidden="true"' in wrapper.group(0)

    def test_it_is_inert_as_well_as_unfocusable(self):
        """`tabindex="-1"` keeps it off the tab ring; `inert` takes it out of
        interaction entirely, for the browsers that support it. A screen reader
        must never offer a person a field whose only correct value is empty."""
        source = FORM.read_text(encoding="utf-8")
        wrapper = re.search(r'<div className="form-aux"[^>]*>', source)
        assert wrapper and re.search(r"\binert\b", wrapper.group(0))
        assert "tabIndex={-1}" in source

    def test_the_wrapper_is_still_off_screen(self):
        css = CSS.read_text(encoding="utf-8")
        rule = re.search(r"\.form-aux\s*\{[^}]*\}", css)
        assert rule and "-9999px" in rule.group(0)


class TestNothingShippedNamesTheTrap:
    """A DOM that says "honeypot" documents the defence to the scraper."""

    @pytest.mark.parametrize("path", [FORM, CSS])
    def test_no_shipped_attribute_or_class_says_honeypot(self, path):
        source = path.read_text(encoding="utf-8")
        # JSX comments and CSS comments never reach the browser; attribute
        # values and selectors do.
        shipped = re.sub(r"\{/\*.*?\*/\}|/\*.*?\*/", "", source, flags=re.S)
        for offender in ('"honeypot"', "field-honeypot", ".honeypot"):
            assert offender not in shipped

    def test_the_visible_label_gives_no_instruction_to_a_reader(self):
        """"Ne pas remplir" told a scraper what the field was for."""
        assert "Ne pas remplir" not in FORM.read_text(encoding="utf-8")


# ─── The wire, and the deploy window ─────────────────────────────────────────

class TestTheRequestBodyToo:
    """The payload travels through the browser, so it names nothing either."""

    def _request(self, **extra):
        from app.api.site import LeadRequest
        return LeadRequest(conversion_type="CONTACT", email="a@b.be",
                                  language="fr", **extra)

    def test_the_new_field_carries_the_decoy_value(self):
        assert self._request(ref_token_2="http://spam.example").decoy_value \
            == "http://spam.example"

    def test_a_page_served_before_this_deploy_is_still_protected(self):
        """`honeypot` stays accepted on purpose.

        Between the API rolling and the browser bundle rolling, a cached page
        posts the old key. Dropping it would leave those visitors with the trap
        silently disabled — a defence that stops working without anything
        failing is worse than one that never existed.
        """
        assert self._request(honeypot="http://spam.example").decoy_value \
            == "http://spam.example"

    def test_an_empty_decoy_is_no_decoy(self):
        assert self._request().decoy_value is None
        assert self._request(ref_token_2="", honeypot="").decoy_value is None

    def test_the_form_posts_the_new_key(self):
        source = FORM.read_text(encoding="utf-8")
        assert "ref_token_2:" in source
        assert "honeypot:" not in source
