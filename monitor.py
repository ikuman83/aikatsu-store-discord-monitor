#!/usr/bin/env python3
"""Watch the official 取扱店舗 listings for store appearances and machine updates."""

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
    # 取扱店舗 results link to detailed machine status in the same page. Details are in
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


def store_listing_status(html: str | bytes, name: str) -> str:
    """Return present/absent/unknown from the official 取扱店舗 search page.

    A missing modal alone is not proof a store is no longer listed.
    """
    soup = BeautifulSoup(html, "html.parser")
    detail_names = [
        compact(heading.get_text(" ", strip=True))
        for heading in soup.select(".modalFilterCol .storeInfoRow .storeColName")
    ]
    if compact(name) in detail_names:
        return "present"
    result_names = [
        compact(heading.get_text(" ", strip=True))
        for heading in soup.select(".resultColBox .storeColName")
    ]
    if compact(name) in result_names:
        return "present"  # listed; machine details may still be unavailable
    body = compact(soup.get_text(" ", strip=True))
    if "指定された条件のお店は見つかりませんでした" in body or (
        "検索結果0件" in body and not result_names
    ):
        return "absent"
    # When other stores are listed, an absent target is meaningful only when
    # this is a normal search results page with a complete result count.
    if result_names and "検索結果" in body and "取扱店舗" in body and "件" in body:
        return "absent"
    return "unknown"


def newly_listed(current: dict[str, str], previous: dict[str, str]) -> list[str]:
    """Notify on first confirmed listing or return from confirmed absence."""
    return [name for name, status in current.items()
            if status == "present" and previous.get(name) != "present"]


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


def updated_since_last_observation(
    machines: list[Machine], last_observed: dict[str, str]
) -> list[Machine]:
    """Catch up on updates missed while GitHub Actions did not run.

    On a first sighting there is no baseline: never guess an old update was new.
    """
    result = []
    for machine in machines:
        old = last_observed.get(machine.key)
        if not old:
            continue
        previous = datetime.fromisoformat(old.replace("Z", "+00:00"))
        if previous.tzinfo is None:
            raise RuntimeError("前回確認した更新日時のタイムゾーンが不正です")
        if previous < machine.updated_at <= machine.checked_at:
            result.append(machine)
    return result


def notification_text(items: list[Machine], unavailable: set[str] | None = None, absent: set[str] | None = None) -> str:
    """Full four-store status, in the requested order, not only changed machines."""
    ordered_names = (
        "タイトーステーション 国分寺店",
        "タイトーステーション 立川北口店",
        "ビックカメラ立川店",
        "namcoららぽーと立川立飛おまけ横丁店",
    )
    unavailable = unavailable or set()
    absent = absent or set()
    lines = []
    for name in ordered_names:
        store_items = sorted(
            (item for item in items if item.store == name),
            key=lambda item: item.number,
        )
        if not store_items:
            if name in absent:
                lines.extend([name, "取扱店舗への掲載なし", "", ""])
                continue
            if name in unavailable:
                lines.extend([name, "情報取得不可", "", ""])
                continue
            raise ParseError(f"通知表示に必要な店舗情報が不足しています: {name}")
        lines.append(name)
        for item in store_items:
            # An item in the official runningList is listed as operating.
            # Never infer "稼働なし" merely from an old update timestamp.
            lines.append(f"{item.number}台目【稼働】 {item.label}")
        lines.extend(["", ""])
    lines.append(f"確認時間：{datetime.now(JST):%Y/%m/%d %H:%M} JST")
    return "\n".join(lines)


def send_discord(webhook: str, message: str) -> None:
    response = requests.post(
        webhook,
        json={"content": message, "allowed_mentions": {"parse": []}},
        headers={"User-Agent": "AikatsuStoreMonitor/1.0"},
        timeout=20,
    )
    response.raise_for_status()



DAILY_STORES = (
    "タイトーステーション 国分寺店",
    "タイトーステーション 立川北口店",
    "ビックカメラ立川店",
    "namcoららぽーと立川立飛おまけ横丁店",
)


def daily_newer_stores(current: list[Machine], baseline: dict[str, str],
                       already_alerted: set[str]) -> list[str]:
    """Compare official timestamps to 08:00; alert at most once per store/day."""
    changed = set()
    for m in current:
        old = baseline.get(m.key)
        if not old or m.store in already_alerted:
            continue
        previous = datetime.fromisoformat(old.replace("Z", "+00:00"))
        if previous.tzinfo is None:
            raise RuntimeError("基準日時にタイムゾーンがありません")
        if previous < m.updated_at <= m.checked_at:
            changed.add(m.store)
    return [name for name in DAILY_STORES if name in changed]


def store_notification(name: str, machines: list[Machine], checked_at: datetime) -> str:
    lines = [name]
    for m in sorted((m for m in machines if m.store == name), key=lambda x: x.number):
        lines.append(f"{m.number}台目【稼働】 {m.label}")
    lines.extend(["", f"確認時間：{checked_at.astimezone(JST):%Y/%m/%d %H:%M} JST"])
    return "\n".join(lines)


def run_daily(webhook: str, schedule: str) -> int:
    if schedule not in {"0 23 * * *", "30,40,50 0 * * *",
                        "0,10,20,30,40,50 1 * * *"}:
        raise RuntimeError(f"未対応のスケジュール: {schedule}")
    checked_at = datetime.now(timezone.utc)
    today = checked_at.astimezone(JST).date().isoformat()
    state = load_state()
    daily = state.get("daily_monitor", {})
    if not isinstance(daily, dict):
        raise RuntimeError("日次監視履歴が不正です")
    if daily.get("date") != today:
        daily = {"date": today, "baseline": {}, "alerted_stores": [], "summary_sent": False}
    machines: list[Machine] = []
    unavailable: set[str] = set()
    absent: set[str] = set()
    for url, names in PAGES.items():
        try:
            html, fetched_at = fetch_page(url)
        except (requests.RequestException, UnicodeError) as exc:
            print(f"WARNING: {url}: {exc}", file=sys.stderr)
            unavailable.update(names)
            continue
        for name in names:
            presence = store_listing_status(html, name)
            if presence == "absent":
                absent.add(name)
            elif presence != "present":
                unavailable.add(name)
            else:
                try:
                    machines.extend(parse_store_page(html, url, (name,), fetched_at))
                except (ParseError, UnicodeError) as exc:
                    print(f"WARNING: {name}: {exc}", file=sys.stderr)
                    unavailable.add(name)

    if schedule == "0 23 * * *":
        if not daily.get("baseline_checked_at"):
            daily["baseline"] = {m.key: m.updated_at.isoformat() for m in machines}
            daily["baseline_checked_at"] = checked_at.isoformat()
            daily["alerted_stores"] = []
            daily["summary_sent"] = False
            print(f"08:00基準を記録: {len(machines)}台")
        else:
            print("本日の08:00基準は記録済みです")
    else:
        baseline = daily.get("baseline", {})
        if not isinstance(baseline, dict):
            raise RuntimeError("08:00基準の形式が不正です")
        alerted = set(daily.get("alerted_stores", []))
        for name in daily_newer_stores(machines, baseline, alerted):
            send_discord(webhook, store_notification(name, machines, checked_at))
            alerted.add(name)
            daily["alerted_stores"] = sorted(alerted)
            state["daily_monitor"] = daily
            save_state(state)
            print(f"08:00より更新: {name}（全筐体を通知）")
        if not baseline:
            print("本日の08:00基準がないため差分通知を省略します")
        # Scheduled 10:50 run. GitHub Actions may be delayed; slot is read
        # from event.schedule, not inferred from actual wall-clock time.
        event_slot = os.environ.get("MONITOR_FINAL_SLOT", "")
        if event_slot == "true" and not daily.get("summary_sent"):
            message = "【本日の稼働状況】\n\n" + notification_text(
                machines, unavailable, absent
            )
            if len(message) > 2000:
                raise RuntimeError("Discord通知文が2000文字を超えました")
            send_discord(webhook, message)
            daily["summary_sent"] = True
            print("10:50最終集計を送信しました")
    daily["last_checked_at"] = checked_at.isoformat()
    state["daily_monitor"] = daily
    save_state(state)
    for name in DAILY_STORES:
        count = sum(m.store == name for m in machines)
        print(f"{name}: {count}台" if count else f"{name}: 情報取得不可/掲載なし")
    return 0


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

    schedule = os.environ.get("MONITOR_SCHEDULE", "").strip()
    if schedule:
        return run_daily(webhook, schedule)

    status_request = os.environ.get("STATUS_REQUEST", "").lower() in {"1", "true", "yes"}
    state = load_state()
    errors: list[str] = []
    unavailable: set[str] = set()
    absent: set[str] = set()
    machines: list[Machine] = []
    current_status: dict[str, str] = {}
    for url, names in PAGES.items():
        try:
            html, checked_at = fetch_page(url)
        except (requests.RequestException, UnicodeError) as exc:
            errors.append(f"{url}: {exc}")
            unavailable.update(names)
            continue
        for name in names:
            status = store_listing_status(html, name)
            if status == "absent":
                current_status[name] = "absent"
                absent.add(name)
                print(f"{name} / 取扱店舗への掲載なし")
                continue
            if status == "unknown":
                unavailable.add(name)
                print(f"{name} / 情報取得不可（掲載を判定できません）")
                continue
            current_status[name] = "present"
            try:
                found = parse_store_page(html, url, (name,), checked_at)
                machines.extend(found)
                print(f"OK: {name}: {len(found)}台を解析")
            except (ParseError, UnicodeError) as exc:
                errors.append(f"{name}: {exc}")
                unavailable.add(name)

    previous_status = state.get("store_presence", {})
    if not isinstance(previous_status, dict):
        raise RuntimeError("店舗掲載履歴の形式が不正です")
    appeared = newly_listed(current_status, previous_status)
    # Avoid repeated listing alerts when the official search briefly flickers
    # between zero results and a populated result.
    last_listing_alerted = state.get("last_listing_alerted", {})
    if not isinstance(last_listing_alerted, dict):
        raise RuntimeError("店舗掲載通知履歴の形式が不正です")
    now = datetime.now(timezone.utc)
    appeared = [
        name for name in appeared
        if not last_listing_alerted.get(name)
        or now - datetime.fromisoformat(
            last_listing_alerted[name].replace("Z", "+00:00")
        ) >= timedelta(hours=24)
    ]
    last_observed = state.get("last_observed_updates", {})
    if not isinstance(last_observed, dict):
        raise RuntimeError("前回確認した筐体更新履歴の形式が不正です")
    fresh = [machine for machine in machines if alert_needed(machine, state["last_alerted"])]
    catch_up = updated_since_last_observation(machines, last_observed)
    ready = list(dict.fromkeys([*fresh, *catch_up]))
    for machine in machines:
        target = "通知対象" if machine in ready else "対象外"
        print(f"{machine.store} / {machine.number}台目 / {machine.label} / {target}")
    for name in sorted(unavailable):
        print(f"{name} / 情報取得不可")
    for name in appeared:
        print(f"{name} / 取扱店舗への掲載を再検知")

    if ready or appeared or status_request:
        if machines:
            message = notification_text(machines, unavailable, absent)
            if appeared:
                message = "【取扱店舗に掲載されました】 " + "、".join(appeared) + "\n\n" + message
            if len(message) > 2000:
                raise RuntimeError("Discord通知文が2000文字を超えました")
            send_discord(webhook, message)
            if not status_request:
                for machine in ready:
                    state["last_alerted"][machine.key] = machine.updated_at.isoformat()
                for name in appeared:
                    last_listing_alerted[name] = now.isoformat()
                state["last_listing_alerted"] = last_listing_alerted
            print("現在状況をDiscordへ送信しました" if status_request else
                  f"更新 {len(ready)}台 / 新規掲載 {len(appeared)}店舗をDiscordへ通知しました")
        elif appeared:
            send_discord(webhook, "【取扱店舗に掲載されました】 " + "、".join(appeared) +
                         f"\n確認時間：{datetime.now(JST):%Y/%m/%d %H:%M} JST")
            if not status_request:
                for name in appeared:
                    last_listing_alerted[name] = now.isoformat()
                state["last_listing_alerted"] = last_listing_alerted
            print("掲載を検知した店舗のみDiscordに通知しました（筐体詳細は取得不可）")
        else:
            print("取得できる筐体がないため通知しません")
    else:
        print("新しい通知対象はありません")

    # Always persist definite observations. Unknown must never overwrite a
    # previous known presence state (e.g. a temporary network error).
    for name, status in current_status.items():
        if not status_request:
            previous_status[name] = status
    if not status_request:
        state["store_presence"] = previous_status
        # Record the exact timestamps after every successful observation,
        # not just when an alert was sent.
        for machine in machines:
            old = last_observed.get(machine.key)
            if not old or machine.updated_at > datetime.fromisoformat(
                old.replace("Z", "+00:00")
            ):
                last_observed[machine.key] = machine.updated_at.isoformat()
        state["last_observed_updates"] = last_observed
        state["last_checked_at"] = now.isoformat()
        save_state(state)

    for message in errors:
        print(f"WARNING: {message}", file=sys.stderr)

    # Commit weekly activity so public GitHub schedules do not go inactive.
    now = datetime.now(timezone.utc)
    last = state.get("last_activity")
    if not last or now - datetime.fromisoformat(last.replace("Z", "+00:00")) >= timedelta(days=7):
        state["last_activity"] = now.isoformat()
        save_state(state)

    # The official pages currently return HTTP 200 and "検索結果 0件".
    # This is a site-data state, not a GitHub Actions execution failure.
    # Record one outage notification after 24h, then remain quiet until recovery.
    if not machines:
        first = state.get("unavailable_since")
        if first is None:
            state["unavailable_since"] = now.isoformat()
            state["unavailable_alerted"] = False
            save_state(state)
            print("監視データを取得できません。24時間継続時に一度だけDiscordへ通知します")
        else:
            since = datetime.fromisoformat(first.replace("Z", "+00:00"))
            if now - since >= timedelta(hours=24) and not state.get("unavailable_alerted", False):
                send_discord(webhook, (
                    "⚠️ アイカツ！監視情報を24時間以上取得できません。"
                    "公式店舗検索が0件などの状態のため、現在は更新通知ができません。"
                    "監視は30分ごとに継続し、情報が復旧すれば自動復帰します。"
                ))
                state["unavailable_alerted"] = True
                save_state(state)
                print("長時間取得不可の通知をDiscordへ1回送信しました")
        return 0

    if state.get("unavailable_since"):
        state.pop("unavailable_since", None)
        state.pop("unavailable_alerted", None)
        save_state(state)
        print("取得できる店舗が復旧しました")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except (requests.RequestException, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
