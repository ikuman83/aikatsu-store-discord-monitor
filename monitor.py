#!/usr/bin/env python3
"""Watch four Aikatsu Encore stores and notify Discord about fresh changes."""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
STATE_PATH = Path(__file__).resolve().parent / "data" / "state.json"
TACHIKAWA_URL = "https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E7%AB%8B%E5%B7%9D&p=1"
KOKUBUNJI_URL = "https://dcd.aikatsu.com/encore/shoplist/list.php?free=%E5%9B%BD%E5%88%86%E5%AF%BA&p=1"
PAGES: dict[str, tuple[str, ...]] = {
    TACHIKAWA_URL: (
        "タイトーステーション 立川北口店",
        "ビックカメラ立川店",
        "namcoららぽーと立川立飛おまけ横丁店",
    ),
    KOKUBUNJI_URL: ("タイトーステーション 国分寺店",),
}


class ParseError(RuntimeError):
    pass


def norm(text: str) -> str:
    return unicodedata.normalize("NFKC", text).strip()


def compact(text: str) -> str:
    return re.sub(r"\s+", "", norm(text))


def age_in_minutes(label: str) -> float | None:
    """Return age only when it unambiguously represents under an hour."""
    value = compact(label)
    if value in {"たった今", "今", "今さっき", "更新直後"}:
        return 0.0
    if value == "数秒前":
        return 0.1
    if value == "数分前":
        return 3.0
    match = re.fullmatch(r"([0-9]+)(秒|分|時間|日|週間|ヶ月|か月|年)前", value)
    if not match:
        return None
    n, unit = int(match.group(1)), match.group(2)
    if unit == "秒":
        return n / 60
    if unit == "分":
        return float(n)
    # "1時間前" could mean anything between 60 and 119 minutes.
    return None


@dataclass(frozen=True)
class Machine:
    store: str
    number: int
    label: str
    url: str
    checked_at: datetime

    @property
    def key(self) -> str:
        return f"{self.store}::{self.number}"

    @property
    def age_minutes(self) -> float | None:
        return age_in_minutes(self.label)

    @property
    def update_estimate(self) -> datetime | None:
        age = self.age_minutes
        return self.checked_at - timedelta(minutes=age) if age is not None else None


def parse_store_page(
    html: str | bytes, url: str, names: tuple[str, ...], checked_at: datetime
) -> list[Machine]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "template"]):
        tag.decompose()
    tokens = [norm(s) for s in soup.stripped_strings]
    if not tokens:
        raise ParseError("ページ本文が空です")

    # Store names may also occur in a summary; use the final occurrence,
    # expected to be the detail heading, to find its machine records.
    positions: dict[str, int] = {}
    for name in names:
        matches = [i for i, token in enumerate(tokens) if compact(name) in compact(token)]
        if not matches:
            raise ParseError(f"対象店舗が見つかりません: {name}")
        positions[name] = matches[-1]

    ordered = sorted(positions.items(), key=lambda pair: pair[1])
    machines: list[Machine] = []
    for i, (name, start) in enumerate(ordered):
        stop = ordered[i + 1][1] if i + 1 < len(ordered) else len(tokens)
        segment = tokens[start:stop]
        current: int | None = None
        found: set[int] = set()
        for j, token in enumerate(segment):
            machine = re.search(r"(?<![0-9])([0-9]+)\s*台目", token)
            if machine:
                current = int(machine.group(1))
                continue
            match = re.search(r"最終更新\s*[:：]?\s*(.*)", token)
            if match and current is not None:
                label = match.group(1).strip()
                if not label and j + 1 < len(segment):
                    label = segment[j + 1].strip()
                if label and current not in found:
                    machines.append(Machine(name, current, label, url, checked_at))
                    found.add(current)
        if not found:
            raise ParseError(f"筐体の最終更新表示が読み取れません: {name}")
    return machines


def fetch_page(url: str) -> tuple[bytes, datetime]:
    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; AikatsuStoreMonitor/1.0)",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        timeout=25,
    )
    response.raise_for_status()
    return response.content, datetime.now(timezone.utc)


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"last_alerted": {}, "last_activity": None}
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        if not isinstance(state.get("last_alerted"), dict):
            raise ValueError("last_alerted is invalid")
        return state
    except (ValueError, OSError) as exc:
        raise RuntimeError("通知履歴が破損したため、重複通知を避けるため停止します") from exc


def save_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def alert_needed(machine: Machine, last_alerted: dict[str, str]) -> bool:
    age = machine.age_minutes
    if age is None or age >= 60:
        return False
    estimated = machine.update_estimate
    assert estimated is not None
    old_value = last_alerted.get(machine.key)
    if not old_value:
        return True
    old = datetime.fromisoformat(old_value.replace("Z", "+00:00"))
    # A few minutes of tolerance for rounded relative-time labels.
    return estimated - old > timedelta(minutes=5)


def notification_text(items: list[Machine]) -> str:
    lines = ["🎴 **アイカツ！アンコール：店舗の最新更新を検知**", ""]
    for item in items:
        lines += [
            f"**{item.store}**（{item.number}台目）",
            f"最終更新：**{item.label}**",
            f"公式ページ：{item.url}",
            "",
        ]
    lines.append(
        f"確認時刻：{datetime.now(JST):%Y/%m/%d %H:%M} JST"
        "（公式サイトの相対時間表示に基づく）"
    )
    return "\n".join(lines)


def send_discord(webhook: str, message: str) -> None:
    response = requests.post(
        webhook,
        json={"content": message, "allowed_mentions": {"parse": []}},
        headers={"User-Agent": "AikatsuStoreMonitor/1.0"},
        timeout=20,
    )
    response.raise_for_status()


def run() -> int:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook.startswith((
        "https://discord.com/api/webhooks/",
        "https://discordapp.com/api/webhooks/",
    )):
        print("ERROR: GitHub Actions Secret DISCORD_WEBHOOK_URLが必要です", file=sys.stderr)
        return 1

    if os.environ.get("TEST_NOTIFICATION", "").lower() in {"1", "true", "yes"}:
        send_discord(
            webhook,
            "🧪 **アイカツ！アンコール監視のテスト通知**\nDiscord通知設定は正常です。",
        )
        print("Discordへのテスト通知を送信しました（履歴は変更しません）")
        return 0

    state = load_state()
    errors: list[str] = []
    machines: list[Machine] = []
    for url, names in PAGES.items():
        try:
            html, checked_at = fetch_page(url)
            found = parse_store_page(html, url, names, checked_at)
            machines.extend(found)
            print(f"OK: {url}: {len(found)}台を解析")
        except (requests.RequestException, ParseError, UnicodeError) as exc:
            errors.append(f"{url}: {exc}")

    ready = [machine for machine in machines if alert_needed(machine, state["last_alerted"])]
    for machine in machines:
        target = "通知対象" if machine in ready else "対象外"
        print(f"{machine.store} / {machine.number}台目 / {machine.label} / {target}")

    if ready:
        groups: list[list[Machine]] = []
        group: list[Machine] = []
        for machine in ready:
            if group and len(notification_text(group + [machine])) > 1900:
                groups.append(group)
                group = []
            group.append(machine)
        if group:
            groups.append(group)
        for group in groups:
            send_discord(webhook, notification_text(group))
            for machine in group:
                timestamp = machine.update_estimate
                assert timestamp is not None
                state["last_alerted"][machine.key] = timestamp.isoformat()
            save_state(state)
        print(f"新しい更新 {len(ready)}台をDiscordへ通知しました")
    else:
        print("新しい通知対象はありません")

    # Commit weekly activity so public GitHub schedules do not go inactive.
    now = datetime.now(timezone.utc)
    last = state.get("last_activity")
    if not last or now - datetime.fromisoformat(last.replace("Z", "+00:00")) >= timedelta(days=7):
        state["last_activity"] = now.isoformat()
        save_state(state)

    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
