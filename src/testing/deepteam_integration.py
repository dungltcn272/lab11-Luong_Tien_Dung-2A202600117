"""
DeepTeam integration helpers for the Lab 11 chatbot.

This module provides:
- Loading the local Vietnamese mock dataset
- Converting dataset rows to attack prompts for the existing pipeline
- Running DeepTeam against the current chatbot via a model callback
- Exporting generated DeepTeam test cases to JSON/CSV for reuse
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Union

CURRENT_FILE = Path(__file__).resolve()
SRC_ROOT = CURRENT_FILE.parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.utils import chat_with_agent


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MOCK_DATASET = PROJECT_ROOT / "data" / "mock_red_blue_team_vi.json"
DEFAULT_DEEPTEAM_OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "deepteam"


try:
    from deepeval import ConversationalGolden, Golden
except ImportError:
    Golden = Any
    ConversationalGolden = Any


def load_mock_dataset(dataset_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load the Vietnamese mock dataset from JSON."""
    path = Path(dataset_path) if dataset_path else DEFAULT_MOCK_DATASET
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def dataset_to_attacks(dataset: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert dataset rows into the attack format used by run_attacks()."""
    attacks = []
    for index, row in enumerate(dataset, start=1):
        attacks.append(
            {
                "id": row.get("id", index),
                "category": row.get("category", "custom_dataset"),
                "input": row.get("prompt", ""),
            }
        )
    return attacks


def generate_payload(
    golden: Union[Golden, ConversationalGolden],
    prompts: Optional[Dict[str, str]] = None,
    hyperparameters: Optional[Dict[str, str]] = None,
    testCaseId: Optional[str] = None,
    turnId: Optional[str] = None,
    state: Optional[Any] = None,
) -> dict:
    """Build payload for DeepEval Golden/ConversationalGolden records."""
    _ = (testCaseId, turnId, state)

    if isinstance(golden, Golden):
        # Construct golden payload for single-turn datasets.
        return {
            "input": golden.input,
            "context": golden.context,
            "prompts": prompts,
            "hyperparameters": hyperparameters,
        }

    if isinstance(golden, ConversationalGolden):
        # Construct conversational golden payload for multi-turn datasets.
        return {
            "turns": golden.turns,
            "conversationContext": golden.context,
            "prompts": prompts,
            "hyperparameters": hyperparameters,
        }

    raise TypeError(
        "golden must be an instance of deepeval.Golden or deepeval.ConversationalGolden."
    )


def export_records_to_csv(records: list[dict[str, Any]], output_path: str | Path) -> Path:
    """Save a list of dict records as CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        path.write_text("", encoding="utf-8")
        return path

    fieldnames: list[str] = []
    seen = set()
    for record in records:
        for key in record.keys():
            if key not in seen:
                seen.add(key)
                fieldnames.append(key)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    return path


def _serialize_test_case(test_case: Any, index: int) -> dict[str, Any]:
    """Convert a DeepTeam RTTestCase-like object into a plain dict."""
    payload = {
        "id": index,
        "vulnerability": str(getattr(test_case, "vulnerability", "")),
        "vulnerability_type": str(getattr(test_case, "vulnerability_type", "")),
        "attack_method": str(getattr(test_case, "attack_method", "")),
        "input": getattr(test_case, "input", "") or "",
        "actual_output": getattr(test_case, "actual_output", "") or "",
        "score": getattr(test_case, "score", None),
        "reason": getattr(test_case, "reason", "") or "",
        "error": getattr(test_case, "error", "") or "",
        "risk_category": str(getattr(test_case, "risk_category", "")),
    }

    turns = getattr(test_case, "turns", None)
    if turns:
        payload["turns"] = [
            {
                "role": getattr(turn, "role", ""),
                "content": getattr(turn, "content", ""),
            }
            for turn in turns
        ]

    metadata = getattr(test_case, "metadata", None)
    if metadata:
        payload["metadata"] = metadata

    return payload


async def generate_deepteam_cases_for_agent(
    agent,
    runner,
    output_dir: str | Path | None = None,
    attacks_per_vulnerability_type: int = 2,
    max_concurrent: int = 2,
) -> tuple[Any, list[dict[str, Any]], Path]:
    """Run DeepTeam against the current chatbot and export test cases locally.

    Returns:
        Tuple of (risk_assessment, exported_test_case_records, output_dir_path)
    """
    try:
        from deepteam import red_team
        from deepteam.frameworks import OWASPTop10
    except ImportError as exc:
        raise ImportError(
            "DeepTeam is not installed. Run `pip install -U deepteam` or install from requirements.txt."
        ) from exc

    async def model_callback(user_input: str) -> str:
        response, _ = await chat_with_agent(agent, runner, user_input)
        return response

    target_output_dir = Path(output_dir) if output_dir else DEFAULT_DEEPTEAM_OUTPUT_DIR
    target_output_dir.mkdir(parents=True, exist_ok=True)

    risk_assessment = red_team(
        model_callback=model_callback,
        framework=OWASPTop10(),
        attacks_per_vulnerability_type=attacks_per_vulnerability_type,
        max_concurrent=max_concurrent,
    )

    exported_records = [
        _serialize_test_case(test_case, index)
        for index, test_case in enumerate(getattr(risk_assessment, "test_cases", []), start=1)
    ]

    if hasattr(risk_assessment, "save"):
        risk_assessment.save(to=str(target_output_dir))

    json_path = target_output_dir / "deepteam_test_cases.json"
    csv_path = target_output_dir / "deepteam_test_cases.csv"
    json_path.write_text(
        json.dumps(exported_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    export_records_to_csv(exported_records, csv_path)

    return risk_assessment, exported_records, target_output_dir
