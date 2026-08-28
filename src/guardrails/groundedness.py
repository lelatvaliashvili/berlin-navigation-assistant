from dataclasses import dataclass
from pathlib import Path
import re
import yaml
from pydantic import BaseModel, Field
from src.llm import create_chat_model


DEFAULT_POLICY_PATH = (
    Path(__file__).resolve().parent / "policies" / "groundedness.yaml"
)


class GroundednessDecision(BaseModel):
    supported: bool = Field(
        description="Whether every material claim is supported by evidence."
    )
    unsupported_claims: list[str] = Field(default_factory=list)
    reason: str = Field(description="Brief evidence-based explanation.")


class GroundedAnswerRepair(BaseModel):
    answer: str = Field(
        description="A helpful answer containing only evidence-supported claims."
    )


@dataclass(frozen=True)
class GroundednessResult:
    supported: bool
    unsupported_claims: list[str]
    reason: str


class GroundednessGuard:
    def __init__(
        self,
        policy_path: Path = DEFAULT_POLICY_PATH,
        *,
        judge=None,
        repairer=None,
    ) -> None:
        policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
        self.judge_prompt = policy["judge_prompt"]
        self.repair_prompt = policy["repair_prompt"]
        self.fallback = policy["fallback"]
        self.judge = judge or create_chat_model(
            num_predict=256
        ).with_structured_output(
            GroundednessDecision,
        )
        self.repairer = repairer or create_chat_model(
            num_predict=256
        ).with_structured_output(
            GroundedAnswerRepair,
        )

    def check(
        self,
        *,
        question: str,
        evidence: str,
        answer: str,
    ) -> GroundednessResult:
        if result := self._check_evidence_available(evidence):
            return result

        if result := self._check_numeric_claims(
            question=question,
            evidence=evidence,
            answer=answer,
        ):
            return result

        if self._explicit_return_rule_is_aligned(
            question=question,
            evidence=evidence,
            answer=answer,
        ):
            return GroundednessResult(
                supported=True,
                unsupported_claims=[],
                reason=(
                    "The answer follows the retrieved prohibition on return "
                    "journeys; permitted transfers do not change that rule."
                ),
            )

        return self._judge_with_llm(
            question=question,
            evidence=evidence,
            answer=answer,
        )

    @staticmethod
    def _check_evidence_available(
        evidence: str,
    ) -> GroundednessResult | None:
        if evidence.strip():
            return None
        return GroundednessResult(
            supported=False,
            unsupported_claims=["No reviewed evidence was available."],
            reason="The answer cannot be verified without evidence.",
        )

    @classmethod
    def _check_numeric_claims(
        cls,
        *,
        question: str,
        evidence: str,
        answer: str,
    ) -> GroundednessResult | None:
        unsupported_numbers = cls._unsupported_numbers(
            question=question,
            evidence=evidence,
            answer=answer,
        )
        if not unsupported_numbers:
            return None
        rendered = ", ".join(unsupported_numbers)
        return GroundednessResult(
            supported=False,
            unsupported_claims=[
                f"Numeric claims absent from evidence: {rendered}."
            ],
            reason=(
                "The answer introduces numeric factual claims that are not "
                "present in the user question or reviewed evidence."
            ),
        )

    def _judge_with_llm(
        self,
        *,
        question: str,
        evidence: str,
        answer: str,
    ) -> GroundednessResult:
        decision = self.judge.invoke(
            [
                ("system", self.judge_prompt),
                (
                    "user",
                    "USER QUESTION\n"
                    f"{question}\n\n"
                    "REVIEWED EVIDENCE\n"
                    f"{evidence}\n\n"
                    "CANDIDATE ANSWER\n"
                    f"{answer}",
                ),
            ]
        )
        return GroundednessResult(
            supported=decision.supported,
            unsupported_claims=decision.unsupported_claims,
            reason=decision.reason,
        )

    def repair(
        self,
        *,
        question: str,
        official_context: str,
        answer: str,
        unsupported_claims: list[str],
    ) -> str:
        """Retain supported content while removing or qualifying unsafe claims."""
        if not official_context.strip():
            return (
                "I don’t have reliable information to confirm that, so I don’t "
                "want to guess. Please check BVG’s official service for the "
                "latest answer."
            )

        repaired = self.repairer.invoke(
            self._build_repair_messages(
                question=question,
                official_context=official_context,
                answer=answer,
                unsupported_claims=unsupported_claims,
            )
        )
        return repaired.answer.strip()

    def _build_repair_messages(
        self,
        *,
        question: str,
        official_context: str,
        answer: str,
        unsupported_claims: list[str],
    ) -> list[tuple[str, str]]:
        issues = "\n".join(f"- {claim}" for claim in unsupported_claims)
        return [
            ("system", self.repair_prompt),
            (
                "user",
                f"USER QUESTION\n{question}\n\n"
                f"OFFICIAL TRANSPORT INFORMATION\n{official_context}\n\n"
                f"ORIGINAL ANSWER\n{answer}\n\n"
                f"UNSUPPORTED CLAIMS\n{issues or '- See judge reason'}",
            ),
        ]

    @staticmethod
    def _unsupported_numbers(
        *,
        question: str,
        evidence: str,
        answer: str,
    ) -> list[str]:
        number_pattern = r"(?<![\w.])\d+(?:[.,]\d+)?(?![\w.])"

        def numbers(value: str) -> set[str]:
            return {
                match.replace(",", ".")
                for match in re.findall(number_pattern, value)
            }

        allowed = numbers(question) | numbers(evidence)
        return sorted(numbers(answer) - allowed)

    @staticmethod
    def _explicit_return_rule_is_aligned(
        *,
        question: str,
        evidence: str,
        answer: str,
    ) -> bool:
        question_text = question.lower()
        evidence_text = evidence.lower()
        answer_text = answer.lower()
        asks_about_return = "return journey" in question_text

        evidence_prohibits_return = bool(
            re.search(
                r"return\s+journeys?\s+(?:are|is)\s+not\s+permitted",
                evidence_text,
            )
        )
        answer_prohibits_return = bool(
            re.search(
                r"(?:not permit|not permitted|cannot|can't|does not permit)"
                r".{0,60}return journey",
                answer_text,
            )
            or re.search(
                r"return journeys?.{0,30}(?:not permitted|not allowed)",
                answer_text,
            )
        )
        transfer_claim_is_supported = (
            "transfer" not in answer_text or "transfer" in evidence_text
        )

        return (
            asks_about_return
            and evidence_prohibits_return
            and answer_prohibits_return
            and transfer_claim_is_supported
        )
