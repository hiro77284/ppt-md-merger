import argparse
import json
import logging
from pathlib import Path

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_BAD_INPUT = 2
EXIT_NOT_FOUND = 3

_LOG_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "error": logging.ERROR,
}


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=_LOG_LEVELS.get(level, logging.INFO),
        format="%(levelname)s: %(message)s",
    )


def emit(
    args: argparse.Namespace,
    status: str,
    command: str,
    input_path: Path,
    output_path: Path,
    dry_run: bool = False,
) -> None:
    if args.json:
        payload: dict = {
            "status": status,
            "command": command,
            "input": str(input_path),
            "output": str(output_path),
        }
        if dry_run:
            payload["dry_run"] = True
        print(json.dumps(payload, ensure_ascii=False))
    elif dry_run:
        msg = f"DRY-RUN: {input_path}\n-> {output_path}"
        print(msg)
        logging.info("%s", msg)
    else:
        msg = f"OK: {input_path}\n-> {output_path}"
        print(msg)
        logging.info("%s", msg)
