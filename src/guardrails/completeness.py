from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from pydantic import BaseModel


DEFAULT_POLICY_PATH = (Path(__file__).resolve().parent/"policies"/"completeness.yaml")


@dataclass(frozen=True)
class CompletenessResult:
    request_type: str
    missing_fields: list[str]

    @property
    def applies(self) -> bool:
        return self.request_type != "other"

    @property
    def complete(self) -> bool:
        return not self.missing_fields


class InformationCompletenessGuard:
    def __init__(
        self,
        policy_path: Path = DEFAULT_POLICY_PATH,
    ) -> None:
        with policy_path.open("r", encoding="utf-8") as file:
            policy = yaml.safe_load(file)

        self.policies = policy["policies"]
        self.fields = policy["fields"]
        self._validate_policy()

    def evaluate(self, request_type: str,
        facts: BaseModel | dict[str, Any],
    ) -> CompletenessResult:
        values = (
            facts.model_dump()
            if isinstance(facts, BaseModel)
            else facts
        )

        policy = self.policies.get(request_type)

        if policy is None:
            return CompletenessResult(
                request_type="other",
                missing_fields=[],
            )

        required = list(policy.get("required", []))

        for condition in policy.get("conditional", []):
            if self._condition_matches(condition["when"], values):
                required.extend(condition.get("required", []))

        missing = [
            field
            for field in dict.fromkeys(required)
            if self._is_missing(values.get(field))
        ]

        return CompletenessResult(
            request_type=request_type,
            missing_fields=missing,
        )

    def clarification(self, result: CompletenessResult) -> str:
        questions = [
            self.fields[field]["clarification"]
            for field in result.missing_fields
        ]
        return "I need more information. " + " ".join(questions)

    def _validate_policy(self) -> None:
        configured_fields = set(self.fields)
        referenced_fields = set()

        for policy in self.policies.values():
            referenced_fields.update(policy.get("required", []))
            for condition in policy.get("conditional", []):
                referenced_fields.update(condition.get("required", []))
                referenced_fields.add(condition["when"]["field"])

        missing_definitions = referenced_fields - configured_fields

        if missing_definitions:
            names = ", ".join(sorted(missing_definitions))
            raise ValueError(
                f"Completeness fields missing from policy: {names}"
            )

    @staticmethod
    def _condition_matches(
        condition: dict[str, Any],
        values: dict[str, Any],
    ) -> bool:
        value = values.get(condition["field"])
        if value is None:
            return False
        if "contains" in condition:
            return condition["contains"].lower() in str(value).lower()
        if "equals" in condition:
            return value == condition["equals"]
        return False

    @staticmethod
    def _is_missing(value: Any) -> bool:
        return value is None or value == "" or value == []
