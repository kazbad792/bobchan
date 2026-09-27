# 朝の金融・経済ニュース → Obsidian

毎朝 6:00 に金融・経済ニュースを RSS で集め、Claude Code (`claude -p`) で日本語に要約して
Obsidian Vault に `Finance News/YYYY-MM-DD 金融ニュース.md` として保存します。

## 必要なもの
- Python 3.9 以上（追加ライブラリ不要）
- [Claude Code](https://claude.com/claude-code) CLI（ログイン済み）
- 朝 6:00 に PC が起動していること（macOS はスリープ中なら復帰時に実行されます）

## セットアップ
```bash
git clone <this repo> ~/bobchan && cd ~/bobchan
cp config.example.env config.env
vi config.env          # OBSIDIAN_VAULT を自分の Vault パスに。CLAUDE_BIN は `which claude` の結果を推奨
./run.sh               # 手動で1回実行して確認（ログは logs/ に出ます）
./install.sh           # 毎朝 6:00 に登録（macOS: launchd / Linux: cron）
```

- 時刻を変える: `./install.sh 7 30`（7:30）
- 登録解除: `./install.sh --uninstall`
- 保存せずに結果だけ見る: `python3 morning_news.py --dry-run`

## カスタマイズ
- **ニュースソース**: `feeds.txt` に RSS/Atom の URL を1行ずつ追加・削除
- **レポートの構成**: `morning_news.py` の `PROMPT` を編集
- **要約なし（見出し一覧のみ）**: `config.env` で `SUMMARIZER=none`

要約に失敗した場合も、見出し一覧だけはノートに保存されます。
