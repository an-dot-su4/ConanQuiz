#!/usr/bin/env python3
"""クイズアプリの単体HTML（`index.html`）を組み立てる。

`src/template.html` の `__QUESTIONS_JSON__` を `data/questions.json` の中身で
置き換え、完結した HTML ドキュメントとして `index.html` に書き出す。
GitHub Pages はこの `index.html` をそのまま配信する。

問題データの正本は `data/questions.json` のままなので、問題を直したら
このスクリプトで再ビルドするだけでアプリに反映される。

使い方:
    python3 scripts/build_app.py
    python3 scripts/build_app.py --check   # 差分があれば終了コード 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "questions.json"
TEMPLATE_PATH = REPO_ROOT / "src" / "template.html"
OUT_PATH = REPO_ROOT / "index.html"
PLACEHOLDER = "__QUESTIONS_JSON__"

DESCRIPTION = (
    "出典付きでダブルチェックした{total}問から出題する、"
    "名探偵コナンの非公式ファンクイズです。"
)

HEAD = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
<meta name="color-scheme" content="light dark">
<meta property="og:title" content="コナン捜査ファイル">
<meta property="og:description" content="{description}">
<meta property="og:type" content="website">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='26'>%F0%9F%94%8E</text></svg>">
<style>
*{{margin:0}}
body{{margin:0;font:14px system-ui,sans-serif}}
img{{max-width:100%}}
[hidden]{{display:none!important}}
</style>
"""

BODY_OPEN = "</head>\n<body>\n"
TAIL = "\n</body>\n</html>\n"


def build() -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    if PLACEHOLDER not in template:
        raise SystemExit(f"テンプレートに {PLACEHOLDER} がありません: {TEMPLATE_PATH}")

    doc = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    # </script> がデータ側に現れると <script> ブロックが途中で閉じてしまうため無害化する
    payload = json.dumps(doc, ensure_ascii=False).replace("</", "<\\/")
    filled = template.replace(PLACEHOLDER, payload)

    # テンプレートは <title>/<link>/<style> の後に本文が続く構成なので、
    # 最初の </style> の直後で head 側と body 側に切り分ける。
    marker = "</style>"
    idx = filled.find(marker)
    if idx < 0:
        raise SystemExit("テンプレートに </style> が見つかりません。")
    head_part = filled[: idx + len(marker)]
    body_part = filled[idx + len(marker):].lstrip("\n")

    description = DESCRIPTION.format(total=doc["meta"]["total"])
    return HEAD.format(description=description) + head_part + BODY_OPEN + body_part + TAIL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="クイズアプリのHTMLをビルドする")
    parser.add_argument("--check", action="store_true",
                        help="書き出さず、既存の index.html との差分の有無だけを判定する")
    args = parser.parse_args(argv)

    html = build()

    if args.check:
        current = OUT_PATH.read_text(encoding="utf-8") if OUT_PATH.exists() else ""
        if current != html:
            print("index.html が data/questions.json / src/template.html と一致しません。"
                  "`python3 scripts/build_app.py` で再ビルドしてください。")
            return 1
        print("index.html は最新です。")
        return 0

    OUT_PATH.write_text(html, encoding="utf-8")
    total = json.loads(DATA_PATH.read_text(encoding="utf-8"))["meta"]["total"]
    print(f"生成: {OUT_PATH}（{total}問 / {len(html):,} バイト）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
