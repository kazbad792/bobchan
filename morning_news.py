#!/usr/bin/env python3
"""金融・経済ニュースを RSS から集め、Claude で要約して Obsidian に書き出す。

標準ライブラリのみで動作する。要約には Claude Code CLI (`claude -p`) を使う。
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (morning-news; +https://obsidian.md)"
MAX_ITEMS_PER_FEED = 30
MAX_SUMMARY_CHARS = 300


@dataclass
class Article:
    title: str
    link: str
    source: str
    published: datetime | None
    summary: str


def load_env(path: Path) -> None:
    """KEY=VALUE 形式のファイルを読み、未設定の環境変数だけ埋める。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = os.path.expandvars(os.path.expanduser(value.strip().strip('"').strip("'")))
        os.environ.setdefault(key.strip(), value)


def load_feeds(path: Path) -> list[str]:
    feeds = []
    for line in path.read_text(encoding="utf-8").splitlines():
        url = line.split("#", 1)[0].strip()
        if url:
            feeds.append(url)
    return feeds


def strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse_date(text: str | None) -> datetime | None:
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(elem: ET.Element, *names: str) -> str | None:
    for child in elem:
        if local_name(child.tag) in names and (child.text or "").strip():
            return child.text
    return None


def parse_feed(xml_bytes: bytes, fallback_source: str) -> list[Article]:
    """RSS 2.0 / RSS 1.0 (RDF) / Atom をまとめて扱う。"""
    root = ET.fromstring(xml_bytes)
    source = fallback_source
    for elem in root.iter():
        if local_name(elem.tag) in ("channel", "feed"):
            source = strip_html(child_text(elem, "title") or "") or fallback_source
            break

    articles = []
    for elem in root.iter():
        if local_name(elem.tag) not in ("item", "entry"):
            continue
        link = child_text(elem, "link")
        if not link:
            for child in elem:
                if local_name(child.tag) == "link" and child.get("href"):
                    if child.get("rel", "alternate") == "alternate":
                        link = child.get("href")
                        break
        articles.append(
            Article(
                title=strip_html(child_text(elem, "title") or ""),
                link=(link or "").strip(),
                source=source,
                published=parse_date(child_text(elem, "pubDate", "date", "published", "updated")),
                summary=strip_html(child_text(elem, "description", "summary", "content") or "")[
                    :MAX_SUMMARY_CHARS
                ],
            )
        )
        if len(articles) >= MAX_ITEMS_PER_FEED:
            break
    return [a for a in articles if a.title]


def fetch(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def collect(feeds: list[str], since: datetime) -> list[Article]:
    seen: set[str] = set()
    result = []
    for url in feeds:
        try:
            items = parse_feed(fetch(url), url)
        except Exception as e:  # 1 つのフィードの失敗で全体を止めない
            print(f"[warn] {url}: {e}", file=sys.stderr)
            continue
        kept = 0
        for a in items:
            # 日付が無い記事は新しいものとして扱う
            if a.published and a.published < since:
                continue
            key = a.link or a.title
            if key in seen:
                continue
            seen.add(key)
            result.append(a)
            kept += 1
        print(f"[info] {url}: {kept} 件", file=sys.stderr)
    result.sort(key=lambda a: a.published or datetime.now(timezone.utc), reverse=True)
    return result


def articles_as_text(articles: list[Article]) -> str:
    lines = []
    for i, a in enumerate(articles, 1):
        when = a.published.astimezone().strftime("%m/%d %H:%M") if a.published else "日時不明"
        lines.append(f"[{i}] {a.title}\n  出典: {a.source} / {when}\n  URL: {a.link}")
        if a.summary:
            lines.append(f"  概要: {a.summary}")
    return "\n".join(lines)


PROMPT = """あなたは日本の個人投資家向けに朝のマーケットブリーフィングを書く金融アナリストです。
以下は過去 {hours} 時間に配信された金融・経済ニュースの見出し一覧です（日本語・英語混在）。
これをもとに、Obsidian に保存する日本語の Markdown レポートを作成してください。

# 出力形式（この構成を厳守。見出しレベルもこの通り）
## 🔑 今朝の3行まとめ
- 最重要ポイントを3つ、各1行で

## 🌍 マクロ経済・金融政策
## 📈 株式市場
## 💱 為替・金利・債券
## 🛢️ コモディティ・暗号資産
## 🏢 企業・業界ニュース
## 👀 今日の注目ポイント

# ルール
- 各セクションは箇条書き。各項目の末尾に出典リンクを [媒体名](URL) の形で付ける
- 同じ話題の重複記事は1項目に統合する
- 該当ニュースが無いセクションは「特になし」と書く
- 一覧に無い情報や数値を創作しない。推測は「〜の可能性」と明示する
- 英語記事は日本語に訳して要約する
- 前置きや締めの挨拶は書かず、「## 🔑 今朝の3行まとめ」から始める

# ニュース一覧
{articles}
"""


def summarize_with_claude(articles: list[Article], hours: int) -> str:
    claude = os.environ.get("CLAUDE_BIN", "claude")
    if not shutil.which(claude):
        raise RuntimeError(f"claude コマンドが見つかりません: {claude}")
    prompt = PROMPT.format(hours=hours, articles=articles_as_text(articles))
    proc = subprocess.run(
        [claude, "-p", "--output-format", "text"],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise RuntimeError(f"claude が失敗しました (exit {proc.returncode}): {proc.stderr.strip()}")
    return proc.stdout.strip()


def headlines_markdown(articles: list[Article]) -> str:
    lines = ["## 📰 見出し一覧"]
    for a in articles:
        when = a.published.astimezone().strftime("%H:%M") if a.published else "--:--"
        lines.append(f"- {when} [{a.title}]({a.link}) — {a.source}")
    return "\n".join(lines)


def build_note(date: datetime, body: str, articles: list[Article], summarizer: str) -> str:
    sources = sorted({a.source for a in articles})
    frontmatter = "\n".join(
        [
            "---",
            f"date: {date:%Y-%m-%d}",
            f"created: {date:%Y-%m-%dT%H:%M:%S%z}",
            "tags: [finance, news, daily-briefing]",
            f"article_count: {len(articles)}",
            f"summarizer: {summarizer}",
            "sources:",
            *[f'  - "{s}"' for s in sources],
            "---",
        ]
    )
    parts = [frontmatter, f"# 金融・経済ニュース {date:%Y-%m-%d}（{'月火水木金土日'[date.weekday()]}）", body]
    if summarizer != "none":
        parts.append("---")
        parts.append(f"<details><summary>元記事 {len(articles)} 件</summary>\n\n"
                     f"{headlines_markdown(articles)}\n\n</details>")
    return "\n\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config.env")
    parser.add_argument("--feeds", type=Path, default=ROOT / "feeds.txt")
    parser.add_argument("--dry-run", action="store_true", help="Obsidian に書かず標準出力に出す")
    args = parser.parse_args()

    load_env(args.config)
    hours = int(os.environ.get("LOOKBACK_HOURS", "24"))
    summarizer = os.environ.get("SUMMARIZER", "claude")
    vault = os.environ.get("OBSIDIAN_VAULT")
    folder = os.environ.get("NEWS_FOLDER", "Finance News")
    if not vault and not args.dry_run:
        print("[error] OBSIDIAN_VAULT が未設定です（config.env を作成してください）", file=sys.stderr)
        return 1

    now = datetime.now().astimezone()
    articles = collect(load_feeds(args.feeds), now - timedelta(hours=hours))
    if not articles:
        print("[error] 記事を1件も取得できませんでした", file=sys.stderr)
        return 1

    body = headlines_markdown(articles)
    used = "none"
    if summarizer == "claude":
        try:
            body = summarize_with_claude(articles, hours)
            used = "claude"
        except Exception as e:
            # 要約に失敗しても見出し一覧だけは残す
            print(f"[warn] 要約に失敗したため見出し一覧のみ保存します: {e}", file=sys.stderr)

    note = build_note(now, body, articles, used)
    if args.dry_run:
        print(note)
        return 0

    out_dir = Path(vault).expanduser() / folder
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{now:%Y-%m-%d} 金融ニュース.md"
    out.write_text(note, encoding="utf-8")
    print(f"[info] 保存しました: {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
