#!/usr/bin/env python3
"""Append newly published Lotto 6/45 draws to the canonical dataset."""

from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


API_URL = "https://dhlottery.co.kr/lt645/selectPstLt645Info.do"
USER_AGENT = "LottoPlusDataUpdater/1.0"


class DrawNotPublished(Exception):
    pass


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=root / "data" / "lotto_draws.json")
    parser.add_argument("--max-new", type=int, default=100)
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=20.0)
    return parser.parse_args()


def normalize(item: dict[str, Any], requested_round: int) -> dict[str, Any]:
    round_number = int(item["ltEpsd"])
    if round_number != requested_round:
        raise ValueError(f"Requested {requested_round}, received {round_number}")
    numbers = [int(item[f"tm{index}WnNo"]) for index in range(1, 7)]
    draw_date = datetime.strptime(str(item["ltRflYmd"]), "%Y%m%d").date().isoformat()
    return {
        "round": round_number,
        "drawDate": draw_date,
        "numbers": numbers,
        "bonus": int(item["bnsWnNo"]),
        "firstPrizeAmount": int(item.get("rnk1WnAmt") or 0),
        "firstPrizeWinners": int(item.get("rnk1WnNope") or 0),
        "firstPrizeTotal": int(item.get("rnk1SumWnAmt") or 0),
    }


def validate_draw(draw: dict[str, Any], expected_round: int) -> None:
    if int(draw["round"]) != expected_round:
        raise ValueError(f"Unexpected round {draw['round']}, expected {expected_round}")
    numbers = [int(number) for number in draw["numbers"]]
    bonus = int(draw["bonus"])
    if len(numbers) != 6 or len(set(numbers)) != 6:
        raise ValueError(f"Round {expected_round}: six unique main numbers required")
    if numbers != sorted(numbers) or any(number not in range(1, 46) for number in numbers):
        raise ValueError(f"Round {expected_round}: invalid main number list")
    if bonus not in range(1, 46) or bonus in numbers:
        raise ValueError(f"Round {expected_round}: invalid bonus number")


def fetch_draw(round_number: int, retries: int, timeout: float) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        query = urlencode({"srchLtEpsd": round_number, "_": int(time.time() * 1000)})
        request = Request(
            f"{API_URL}?{query}",
            headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
            items = ((payload.get("data") or {}).get("list") or [])
            if not items:
                raise DrawNotPublished(f"Round {round_number} is not published")
            draw = normalize(items[0], round_number)
            validate_draw(draw, round_number)
            return draw
        except DrawNotPublished:
            raise
        except (HTTPError, URLError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as error:
            last_error = error
            if attempt < retries:
                delay = min(8.0, 0.5 * (2 ** (attempt - 1))) + random.uniform(0.0, 0.25)
                time.sleep(delay)
    raise RuntimeError(f"Failed to fetch round {round_number}: {last_error}")


def write_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
        file.write("\n")
    temporary.replace(path)


def main() -> int:
    args = parse_args()
    data_path = args.data.resolve()
    with data_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    draws = payload["draws"]
    if not draws:
        raise ValueError("Canonical dataset is empty")
    latest_round = int(draws[-1]["round"])
    added: list[dict[str, Any]] = []

    for round_number in range(latest_round + 1, latest_round + args.max_new + 1):
        try:
            draw = fetch_draw(round_number, args.retries, args.timeout)
        except DrawNotPublished:
            break
        if datetime.strptime(draw["drawDate"], "%Y-%m-%d").date() <= datetime.strptime(
            draws[-1]["drawDate"], "%Y-%m-%d"
        ).date():
            raise ValueError(f"Round {round_number}: date is not newer than previous round")
        draws.append(draw)
        added.append(draw)

    if not added:
        print(f"No new draw. Latest round remains {latest_round}.")
        return 0

    payload["generatedAt"] = datetime.now(ZoneInfo("Asia/Seoul")).isoformat(timespec="seconds")
    payload["startRound"] = int(draws[0]["round"])
    payload["endRound"] = int(draws[-1]["round"])
    payload["drawCount"] = len(draws)
    write_atomic(data_path, payload)
    print(f"Added {len(added)} draw(s): {added[0]['round']}~{added[-1]['round']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

