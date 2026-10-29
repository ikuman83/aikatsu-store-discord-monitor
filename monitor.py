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


@dataclass(frozen=True)
class Machine:
    store: str
    number: int
    label: str
    url: str
    checked_at: datetime
    updated_at: datetime

    @property
    def key(self) -> str:
        return f"{self.store}::{self.number}"

    @property
    def age_minutes(self) -> float:
        return (self.checked_at - self.updated_at).total_seconds() / 60

    @property
    def update_estimate(self) -> datetime:
        # Kept for compatibility with persisted state from earlier versions.
        return self.updated_at


def parse_timestamp(raw: str) -> datetime:
    # The site's span.timeago has a JST timestamp in title, for example
    # title="2026-10-2820:23:02". Preserve seconds to prevent duplicates.
    try:
        value = re.sub(r"\s+", "", raw)
        dt = datetime.strptime(value, "%Y-%m-%d%H:%M:%S")
        return dt.replace(tzinfo=JST).astimezone(timezone.utc)
    except ValueError as exc:
        raise ParseError(f"更新日時が読めません: {raw!r}") from exc


def parse_store_page(
    html: str | bytes, url: str, names: tuple[str, ...], checked_at: datetime
) -> list[Machine]:
    soup = BeautifulSoup(html, "html.parser")
    machines: list[Machine] = []
    # The search results only list the stores. Machine information is in
    # div.modalFilterCol -> ul.runningList -> li.runningItem.
    modals = soup.select("div.modalFilterCol")
    for name in names:
        exact_modals = []
        for modal in modals:
            heading = modal.select_one(".storeInfoRow .storeColName")
            if heading and compact(heading.get_text(" ", strip=True)) == compact(name):
                exact_modals.append(modal)
        if len(exact_modals) != 1:
            raise ParseError(f"店舗詳細が一意に見つかりません: {name} (件数={len(exact_modals)})")
        items = exact_modals[0].select("li.runningItem")
        if not items:
            raise ParseError(f"筐体が見つかりません: {name}")
        seen: set[int] = set()
        for item in items:
            num = item.select_one(".runningItemNum .num")
            timeago = item.select_one(".runningItemTime .timeago")
            if not num or not timeago:
                raise ParseError(f"筐体番号または更新日時がありません: {name}")
            try:
                number = int(compact(num.get_text()))
            except ValueError as exc:
                raise ParseError(f"筐体番号が不正です: {name}") from exc
            if number in seen:
                raise ParseError(f"筐体番号が重複しています: {name} {number}台目")
            seen.add(number)
            updated_at = parse_timestamp(timeago.get("title", ""))
            label = timeago.get_text(" ", strip=True)
            if not label:
                raise ParseError(f"相対更新時間が空です: {name} {number}台目")
            machines.append(Machine(name, number, label, url, checked_at, updated_at))
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
    # A newly reported update must be within the last 60 minutes.
    age = (machine.checked_at - machine.updated_at).total_seconds()
    if age < 0 or age > 60 * 60:
        return False
    old_value = last_alerted.get(machine.key)
    if not old_value:
        return True
    old = datetime.fromisoformat(old_value.replace("Z", "+00:00"))
    return machine.updated_at > old


def notification_text(items: list[Machine]) -> str:
    """Full four-store status, in the requested order, not only changed machines."""
    ordered_names = (
        "タイトーステーション 国分寺店",
        "タイトーステーション 立川北口店",
        "ビックカメラ立川店",
        "namcoららぽーと立川立飛おまけ横丁店",
    )
    lines = []
    for name in ordered_names:
        store_items = sorted(
            (item for item in items if item.store == name),
            key=lambda item: item.number,
        )
        if not store_items:
            raise ParseError(f"通知表示に必要な店舗情報が不足しています: {name}")
        lines.append(name)
        for item in store_items:
            # An item in the official runningList is listed as operating.
            # Never infer "稼働なし" merely from an old update timestamp.
            lines.append(f"{item.number}台目【稼働】 {item.label}")
        lines.extend(["", ""])
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

    status_request = os.environ.get("STATUS_REQUEST", "").lower() in {"1", "true", "yes"}
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

    if (ready or status_request) and not errors:
        message = notification_text(machines)
        if len(message) > 2000:
            raise RuntimeError("Discord通知文が2000文字を超えました")
        send_discord(webhook, message)
        if not status_request:
            for machine in ready:
                state["last_alerted"][machine.key] = machine.updated_at.isoformat()
            save_state(state)
        print("現在状況をDiscordへ送信しました" if status_request else f"新しい更新 {len(ready)}台を検知し、全店舗の状態をDiscordへ通知しました")
    elif ready:
        print("サイト取得に失敗した店舗があるため、不完全な一覧は通知しません")
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
