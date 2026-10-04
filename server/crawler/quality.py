"""Conservative, configurable extracted-content checks (not relevance ranking)."""
from dataclasses import dataclass
import math
import re

from .fetch import CrawlError


@dataclass
class QualityConfig:
    enabled: bool = True
    min_characters: int = 300
    min_words: int = 60
    min_unique_words: int = 25
    min_unique_ratio: float = 0.08
    max_boilerplate_ratio: float = 0.65
    max_navigation_ratio: float = 0.65
    max_repeated_line_ratio: float = 0.60

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError("quality.enabled must be boolean")
        for key in ("min_characters", "min_words", "min_unique_words"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise ValueError(f"quality.{key} must be positive")
        for key in ("min_unique_ratio", "max_boilerplate_ratio", "max_navigation_ratio", "max_repeated_line_ratio"):
            value = getattr(self, key)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"quality.{key} must be between zero and one")


@dataclass(frozen=True)
class QualityDecision:
    accepted: bool
    reason: str | None
    metrics: dict


class QualityRejected(CrawlError):
    def __init__(self, decision):
        self.decision = decision
        super().__init__(decision.reason)


_WORDS = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)
_SOFT_TITLE = re.compile(r"^(?:page (?:not found|does not exist)|404(?:\s*[-:]?\s*(?:error|page not found|not found))?|requested page (?:not found|unavailable))[.! ]*$", re.I)
_ERROR_TITLE = re.compile(r"^(?:access denied|forbidden|service unavailable|internal server error|just a moment|verify you are human|request blocked|too many requests)[.! ]*$", re.I)
_BOILERPLATE = re.compile(r"cookie (?:policy|preferences|consent)|accept all cookies|privacy policy|terms (?:of use|and conditions)|all rights reserved|subscribe to (?:our|the) newsletter|enable javascript|verify you are human", re.I)
_NAVIGATION = re.compile(r"^(?:home|menu|next|previous|log in|sign in|sign up|search|contact us|about us|table of contents|skip to content|related articles|share|follow us)$", re.I)


def assess_quality(document, config=None):
    config = config or QualityConfig()
    text = document.get("text", "")
    words = [w.casefold() for w in _WORDS.findall(text)]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    total = max(1, sum(len(line) for line in lines))
    unique = len(set(words))
    metrics = {"characters": len(text.strip()), "words": len(words), "unique_words": unique,
               "unique_ratio": unique / max(1, len(words)),
               "boilerplate_ratio": sum(len(line) for line in lines if _BOILERPLATE.search(line)) / total,
               "navigation_ratio": sum(len(line) for line in lines if _NAVIGATION.fullmatch(line)) / total,
               "repeated_line_ratio": 1 - sum(len(line) for line in set(lines)) / total if lines else 0}
    reason = None
    # Match an error title/leading heading, not a technical article discussing HTTP errors.
    title = document.get("title", "").split("|")[0].strip()
    lead = lines[0] if lines else ""
    if not config.enabled:
        return QualityDecision(True, None, metrics)
    if not words:
        reason = "empty_content"
    elif _SOFT_TITLE.fullmatch(title) or (_SOFT_TITLE.fullmatch(lead) and len(words) < 160):
        reason = "soft_404"
    elif _ERROR_TITLE.fullmatch(title) or (_ERROR_TITLE.fullmatch(lead) and len(words) < 160):
        reason = "error_page"
    elif metrics["boilerplate_ratio"] > config.max_boilerplate_ratio or metrics["repeated_line_ratio"] > config.max_repeated_line_ratio:
        reason = "boilerplate"
    elif metrics["navigation_ratio"] > config.max_navigation_ratio:
        reason = "navigation_content"
    elif len(words) < config.min_words and metrics["characters"] < config.min_characters:
        reason = "too_short"
    elif unique < config.min_unique_words or (metrics["unique_ratio"] < config.min_unique_ratio and unique < 2 * config.min_unique_words):
        reason = "insufficient_content"
    return QualityDecision(reason is None, reason, metrics)


def require_quality(document, config):
    decision = assess_quality(document, config)
    if not decision.accepted:
        raise QualityRejected(decision)
    return decision
