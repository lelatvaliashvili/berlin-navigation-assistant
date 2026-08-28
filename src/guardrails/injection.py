import os
import re
from dataclasses import dataclass
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from guardrails.guard import Guard
from guardrails.settings import settings
from guardrails.types.on_fail import OnFailAction
from guardrails.validator_base import Validator, register_validator
from guardrails_ai.types import FailResult, PassResult


settings.rc.enable_metrics = False
settings.disable_tracing = True


INJECTION_PATTERNS = (
    r"\bsystem\s+override\b",
    r"\bignore\s+(?:the\s+)?(?:provided|retrieved|stored|system)\b",
    r"\b(?:previous|stored)\s+(?:bvg\s+)?rules?\s+(?:are\s+)?"
    r"(?:outdated|invalid|no\s+longer\s+valid)\b",
    r"\b(?:rules?|policy)\s+(?:changed|now)\b",
    r"\bi\s+work\s+for\s+bvg\b",
    r"\buse\s+only\s+(?:your|pretrained)\s+(?:own\s+)?knowledge\b",
    r"\bexpired\s+tickets?.{0,60}\b(?:grace|30[ -]minute)\b",
    r"\b(?:grace|30[ -]minute).{0,60}\bexpired\s+tickets?\b",
    r"\bthose\s+30\s+minutes\b",
)


@register_validator(
    name="berlin-navigation/prompt-injection-authority",
    data_type="string",
)

class PromptInjectionAuthorityValidator(Validator):
    def _validate(self, value: str, metadata: dict):
        del metadata
        matched = [
            pattern
            for pattern in INJECTION_PATTERNS
            if re.search(pattern, value, flags=re.IGNORECASE | re.DOTALL)
        ]
        if matched:
            return FailResult(
                error_message=(
                    "The message attempts to override trusted transport "
                    "policy or claim unsupported authority."
                ),
                metadata={"matched_patterns": matched},
            )
        return PassResult()


@dataclass(frozen=True)
class InjectionCheck:
    blocked: bool
    reason: str | None = None


class PromptInjectionGuard:
    refusal = (
        "I can’t accept user-provided instructions or authority claims as "
        "official transport policy. I’ll rely on the reviewed BVG information "
        "available to this assistant."
    )

    def __init__(self) -> None:
        self.guard = Guard().use(
            PromptInjectionAuthorityValidator(
                on_fail=OnFailAction.NOOP,
            )
        )

    def check(self, message: str) -> InjectionCheck:
        outcome = self.guard.validate(message)

        if outcome.validation_passed:
            return InjectionCheck(blocked=False)

        return InjectionCheck(blocked=True, reason="untrusted_policy_override")
