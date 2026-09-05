#!/usr/bin/env python3
"""`data/questions.json` から人間が読める `docs/quiz-bank.md` を生成する。

questions.json が唯一の正本（single source of truth）で、quiz-bank.md はその閲覧用ビュー。
手でどちらかだけを直すと内容がずれるため、必ずこのスクリプトで再生成すること。
ずれていないかは `scripts/verify_quiz.py` が検査する。

使い方:
    python3 scripts/render_quiz.py           # 書き出す
    python3 scripts/render_quiz.py --check   # 差分があれば終了コード 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "questions.json"
MD_PATH = REPO_ROOT / "docs" / "quiz-bank.md"

HEADER = """# 名探偵コナン クイズ問題集（全{total}問）

> ⚠️ **このファイルは自動生成です。直接編集しないでください。**
> 正本は [`questions.json`](../data/questions.json) です。編集後は
> `python3 scripts/render_quiz.py` で再生成してください。

掲載しているのはすべて **2系統以上の独立した情報源で照合済み**（信頼度 A / B）の問題です。
情報源が食い違ったものは [`UNVERIFIED.md`](./UNVERIFIED.md) に隔離してあり、ここには含まれません。

- **総数：{total}問**（初級 {beginner}問／中級 {intermediate}問／上級 {advanced}問）
- 最終更新：{updated}

---

## アプリで使うには

ランダム出題には [`questions.json`](../data/questions.json) を読み込んでください。
スキーマと実装例は [`06-quiz-data-format.md`](./06-quiz-data-format.md) にあります。

---
"""

FOOTER = """
---

## 出題時のチェックリスト

- [ ] その事実は [`UNVERIFIED.md`](./UNVERIFIED.md) に載っていないか？
- [ ] `volatile: true` の問題を出すとき、`asOf` の時点を問題文に含めたか？
- [ ] 選択肢をシャッフルしているか？（データ側でも正解位置は分散させてあるが、二重に担保する）
- [ ] 誤答が、別の問いに対する正しい情報になっていないか？
"""


def render(doc: dict) -> str:
    meta = doc["meta"]
    counts = meta["countsByDifficulty"]
    out = [HEADER.format(
        total=meta["total"],
        beginner=counts.get("beginner", 0),
        intermediate=counts.get("intermediate", 0),
        advanced=counts.get("advanced", 0),
        updated=meta["updated"],
    )]

    for diff in ("beginner", "intermediate", "advanced"):
        label = next(d["label"] for d in meta["difficulties"] if d["key"] == diff)
        rows = [q for q in doc["questions"] if q["difficulty"] == diff]
        out.append(f"\n## 【{label}】{len(rows)}問\n")
        for q in rows:
            out.append(f"\n### {q['id']}　{q['question']}\n")
            out.append(f"`{q['categoryLabel']}`　信頼度 **{q['confidence']}**"
                       + ("　⏳ **要時点明記**" if q.get("volatile") else "") + "\n")
            for i, c in enumerate(q["choices"]):
                out.append(f"{i + 1}. {c}")
            out.append(f"\n<details><summary>答えを見る</summary>\n")
            out.append(f"\n**正解：{q['answerIndex'] + 1}. {q['answer']}**\n")
            out.append(f"\n{q['explanation']}\n")
            srcs = "　".join(f"[出典{i + 1}]({s})" for i, s in enumerate(q["sources"]))
            out.append(f"\n{srcs}\n")
            out.append("\n</details>\n")

    out.append(FOOTER)
    return "\n".join(out).replace("\n\n\n", "\n\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="quiz-bank.md を questions.json から生成する")
    parser.add_argument("--check", action="store_true",
                        help="書き出さず、既存ファイルとの差分の有無だけを判定する")
    args = parser.parse_args(argv)

    doc = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    text = render(doc)

    if args.check:
        current = MD_PATH.read_text(encoding="utf-8") if MD_PATH.exists() else ""
        if current != text:
            print("quiz-bank.md が questions.json と一致しません。"
                  "`python3 scripts/render_quiz.py` で再生成してください。")
            return 1
        print("quiz-bank.md は questions.json と一致しています。")
        return 0

    MD_PATH.write_text(text, encoding="utf-8")
    print(f"生成: {MD_PATH}（{doc['meta']['total']}問）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
