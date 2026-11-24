"""Opt-in real-model evaluation; performs no approval or provider write."""

import argparse
from pathlib import Path

from agent_service.evaluation import SCENARIOS, evaluate
from agent_service.main import build_agent_service


def main() -> None:
    """Run an explicitly selected scenario and write sanitized JSONL evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=[scenario.name for scenario in SCENARIOS])
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-model-calls", action="store_true")
    arguments = parser.parse_args()
    if not arguments.allow_model_calls:
        parser.error(
            "--allow-model-calls is required because evaluation can incur cost"
        )
    scenario = next(item for item in SCENARIOS if item.name == arguments.scenario)
    service = build_agent_service()
    records = evaluate(
        scenario,
        attempts=arguments.attempts,
        run=service.run,
        definitions=service.tool_definitions(),
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        "".join(record.model_dump_json() + "\n" for record in records),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
