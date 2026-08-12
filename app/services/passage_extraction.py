"""Passage extraction — the first stage of the Phase 3.1 evidence model.

The Phase 3 live run handed whole page excerpts to claim-risk classification, and
the excerpts looked like this:

    "Aller au contenu\\n\\nEnergy Village\\n\\n# Prix Panneaux Solaires 2026 …"
    "La boutique ne fonctionnera pas correctement dans le cas où les cookies …"
    "ChatGPTClaudePerplexityGoogle AI Mode\\n\\nVous souhaitez installer …"

Two things went wrong as a result. Risk classification degenerated into scanning
2 KB of text for a risky word — 9 of 10 excerpts came out HIGH — and relevance
became trivially easy to satisfy, since 2 KB of on-topic prose covers any query's
topic tokens.

This module cuts an excerpt into passages and drops the furniture first. It is
deterministic and conservative: when a block is ambiguous it is **kept**, because
discarding real evidence is worse than carrying a little noise into a stage that
can still reject it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# Boilerplate phrases, matched case- and accent-insensitively. Multilingual for
# the BE pilot. This is a denylist of *furniture*, never of topics.
_BOILERPLATE_PHRASES = (
    # navigation / skip links
    "aller au contenu", "skip to content", "naar de inhoud", "menu principal",
    "retour en haut", "back to top", "lire la suite", "read more",
    # cookie and consent banners
    "cookie", "cookies", "consentement", "accepter les cookies",
    "la boutique ne fonctionnera pas",
    # legal / footer furniture
    "tous droits reserves", "all rights reserved", "mentions legales",
    "politique de confidentialite", "privacy policy", "conditions generales",
    "plan du site", "sitemap",
    # social / sharing / newsletter
    "partager sur", "share on", "suivez-nous", "follow us", "newsletter",
    "inscrivez-vous a notre", "abonnez-vous",
    # AI-tool menus seen live
    "chatgpt", "perplexity", "google ai mode",
    # commerce furniture
    "livraison gratuite", "paiements securises", "ajouter au panier",
    "add to cart", "votre panier",
)

# A block that is mostly punctuation, digits or single words is furniture:
# breadcrumbs, price tiles, menu lists.
_MIN_PASSAGE_CHARS = 40
_MIN_PASSAGE_WORDS = 8
_MAX_PASSAGE_CHARS = 600

_BLOCK_SPLIT = re.compile(r"\n\s*\n|\r\n\s*\r\n")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;:])\s+(?=[A-ZÀ-ÿ0-9])")
_MARKDOWN_NOISE = re.compile(r"^\s*(#{1,6}\s*|[-*+]\s+|\d+[.)]\s+|>\s*)")
_URL_OR_MAIL = re.compile(r"https?://\S+|\S+@\S+\.\S+")


@dataclass(frozen=True)
class Passage:
    """A coherent chunk of retrieved text, with its position in the source."""

    text: str
    offset: int
    source_ref: str
    kept: bool = True
    drop_reason: str | None = None

    def as_dict(self) -> dict:
        return {"text": self.text, "offset": self.offset,
                "source_ref": self.source_ref, "kept": self.kept,
                "drop_reason": self.drop_reason}


@dataclass
class PassageSet:
    source_ref: str
    passages: list[Passage] = field(default_factory=list)
    dropped: list[Passage] = field(default_factory=list)

    @property
    def kept_text(self) -> str:
        return " ".join(p.text for p in self.passages)

    def summary(self) -> dict:
        reasons: dict[str, int] = {}
        for passage in self.dropped:
            reasons[passage.drop_reason or "unknown"] = \
                reasons.get(passage.drop_reason or "unknown", 0) + 1
        return {"source_ref": self.source_ref, "kept": len(self.passages),
                "dropped": len(self.dropped), "drop_reasons": reasons}


def _fold(text: str) -> str:
    """Casefold and strip accents, for phrase matching only."""
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _is_boilerplate(block: str) -> str | None:
    """Return a drop reason, or None to keep. Conservative by design."""
    folded = _fold(block)
    stripped = block.strip()

    if len(stripped) < _MIN_PASSAGE_CHARS:
        return "too_short"

    words = stripped.split()
    if len(words) < _MIN_PASSAGE_WORDS:
        return "too_few_words"

    for phrase in _BOILERPLATE_PHRASES:
        if phrase in folded:
            # A long, substantive block that merely mentions cookies in passing is
            # not a cookie banner. Only short blocks are dropped on a phrase hit.
            if len(words) < 40:
                return f"boilerplate:{phrase}"

    letters = sum(1 for c in stripped if c.isalpha())
    if letters / max(len(stripped), 1) < 0.5:
        # Price tiles and spec tables: "4.400 €  625 €/an  7 ans  5 kWh".
        return "low_alpha_ratio"

    # A block with no sentence-ending punctuation and many line breaks is a menu.
    if "." not in stripped and stripped.count("\n") >= 2:
        return "unpunctuated_list"

    return None


def _clean(text: str) -> str:
    text = _MARKDOWN_NOISE.sub("", text)
    text = _URL_OR_MAIL.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_passages(excerpt: str, *, source_ref: str) -> PassageSet:
    """Split a retrieved excerpt into passages, dropping page furniture.

    Blocks are split on blank lines first (how page text arrives), then long
    blocks are split into sentence groups so a single passage stays quotable as
    "the exact supporting passage" for a claim.
    """
    result = PassageSet(source_ref=source_ref)
    if not excerpt or not excerpt.strip():
        return result

    offset = 0
    for raw_block in _BLOCK_SPLIT.split(excerpt):
        block_offset = excerpt.find(raw_block, offset)
        offset = max(offset, block_offset + len(raw_block)) if block_offset >= 0 else offset

        # Line-level furniture removal inside the block, before judging it.
        lines = [ln for ln in raw_block.splitlines() if ln.strip()]
        keepable = []
        for line in lines:
            folded = _fold(line)
            if len(line.split()) < 5 and any(p in folded for p in _BOILERPLATE_PHRASES):
                continue
            keepable.append(line)
        block = "\n".join(keepable)

        reason = _is_boilerplate(block)
        if reason:
            result.dropped.append(Passage(
                text=_clean(block)[:200], offset=max(block_offset, 0),
                source_ref=source_ref, kept=False, drop_reason=reason))
            continue

        cleaned = _clean(block)
        if not cleaned:
            continue

        if len(cleaned) <= _MAX_PASSAGE_CHARS:
            result.passages.append(Passage(text=cleaned,
                                           offset=max(block_offset, 0),
                                           source_ref=source_ref))
            continue

        # Long block: group sentences into passages that stay quotable.
        current = ""
        for sentence in _SENTENCE_SPLIT.split(cleaned):
            if len(current) + len(sentence) + 1 > _MAX_PASSAGE_CHARS and current:
                result.passages.append(Passage(text=current.strip(),
                                               offset=max(block_offset, 0),
                                               source_ref=source_ref))
                current = sentence
            else:
                current = f"{current} {sentence}".strip()
        if current.strip():
            result.passages.append(Passage(text=current.strip(),
                                           offset=max(block_offset, 0),
                                           source_ref=source_ref))

    return result
