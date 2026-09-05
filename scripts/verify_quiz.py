#!/usr/bin/env python3
"""名探偵コナン クイズデータの機械的検査（ダブルチェック L1）。

`data/questions.json` の構造・整合性・出題品質を検査する。

Web アクセスは行わない。ここで分かるのは「データが自己矛盾していないか」だけで、
記載された事実そのものが正しいかは、収集時に別ソースで照合済み（confidence 欄）。
情報源が食い違った事項は `docs/UNVERIFIED.md` に隔離してあり、本データには含めない。

主な検査:
  - id の重複、書式
  - choices がちょうど4つで重複がないか
  - answerIndex が範囲内で、choices[answerIndex] == answer か
  - difficulty / category が meta の定義と一致するか
  - confidence が A / B のみか（C 以下はクイズに使わない方針）
  - sources が1件以上あり http(s) URL か
    （SOURCE_GATE_FROM 以降の問題は2件必須＝ERROR。それ以前の既存分は WARN）
  - meta の集計（total / countsByDifficulty / countsByCategory）が実データと一致するか
  - 問題文の重複
  - 正解位置の偏り（ランダム出題時の位置バイアス検出）
  - 正解が他の選択肢の部分文字列になっていないか（消去法で当たる問題の検出）
  - quiz-bank.md が questions.json から再生成した内容と一致するか（ドキュメントのずれ検出）

使い方:
    python3 scripts/verify_quiz.py
    python3 scripts/verify_quiz.py --json
    python3 scripts/verify_quiz.py --strict     # WARN も失敗扱い

終了コード: ERROR が1件でもあれば 1（--strict なら WARN も 1）、なければ 0。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = REPO_ROOT / "data" / "questions.json"

ID_RE = re.compile(r"^conan-\d{3}$")
URL_RE = re.compile(r"^https?://")
ALLOWED_CONFIDENCE = {"A", "B"}
CHOICE_COUNT = 4
# この番号以降に追加した問題は、出典URL 2件以上を必須とする。
# それ以前の問題は、事実の照合はしたものの URL を1件しか記録できていないものが
# 残っており、遡って直すまでは WARN 扱いにしている（README の「0. 照合と出典の記録」参照）。
SOURCE_GATE_FROM = 121
# 正解位置の偏り警告のしきい値（理想は 1/4 = 25%）
POSITION_BIAS_TOLERANCE = 0.15


class Issue:
    def __init__(self, severity: str, target: str, check: str, message: str):
        self.severity = severity
        self.target = target
        self.check = check
        self.message = message

    def as_dict(self) -> dict:
        return {
            "severity": self.severity,
            "target": self.target,
            "check": self.check,
            "message": self.message,
        }

    def __str__(self) -> str:
        return f"[{self.severity}] {self.target} ({self.check}): {self.message}"


def load(path: Path, issues: list[Issue]) -> dict | None:
    if not path.exists():
        issues.append(Issue("ERROR", str(path), "file", "questions.json が見つかりません。"))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        issues.append(Issue("ERROR", str(path), "json", f"JSON として読めません: {exc}"))
        return None


def check_question(q: dict, idx: int, diffs: set[str], cats: set[str],
                   issues: list[Issue]) -> None:
    qid = q.get("id") or f"#{idx}"

    if not isinstance(q.get("id"), str) or not ID_RE.match(q["id"]):
        issues.append(Issue("ERROR", qid, "id", "id が conan-000 形式ではありません。"))

    for field in ("question", "explanation", "answer"):
        if not isinstance(q.get(field), str) or not q[field].strip():
            issues.append(Issue("ERROR", qid, f"field/{field}", f"{field} が空です。"))

    if q.get("difficulty") not in diffs:
        issues.append(Issue("ERROR", qid, "difficulty",
                            f"未定義の difficulty です: {q.get('difficulty')!r}"))
    if q.get("category") not in cats:
        issues.append(Issue("ERROR", qid, "category",
                            f"未定義の category です: {q.get('category')!r}"))

    choices = q.get("choices")
    if not isinstance(choices, list) or len(choices) != CHOICE_COUNT:
        issues.append(Issue("ERROR", qid, "choices",
                            f"選択肢は{CHOICE_COUNT}つ必要です（現在 "
                            f"{len(choices) if isinstance(choices, list) else '不正'}）。"))
        return

    if any(not isinstance(c, str) or not c.strip() for c in choices):
        issues.append(Issue("ERROR", qid, "choices", "空の選択肢があります。"))
    if len(set(choices)) != len(choices):
        dup = [c for c, n in Counter(choices).items() if n > 1]
        issues.append(Issue("ERROR", qid, "choices", f"選択肢が重複しています: {dup}"))
    for c in choices:
        if isinstance(c, str) and c != c.strip():
            issues.append(Issue("WARN", qid, "choices",
                                f"選択肢の前後に空白があります: {c!r}"))

    ai = q.get("answerIndex")
    if not isinstance(ai, int) or not 0 <= ai < len(choices):
        issues.append(Issue("ERROR", qid, "answerIndex",
                            f"answerIndex が範囲外です: {ai!r}"))
    elif choices[ai] != q.get("answer"):
        issues.append(Issue("ERROR", qid, "answerIndex",
                            f"choices[{ai}]={choices[ai]!r} が answer="
                            f"{q.get('answer')!r} と一致しません。"))
    else:
        # 正解が他の選択肢に含まれていると、消去法や部分一致で当てられてしまう
        answer = choices[ai]
        for j, c in enumerate(choices):
            if j == ai:
                continue
            if answer in c or c in answer:
                issues.append(Issue("WARN", qid, "choices/overlap",
                                    f"正解 {answer!r} と誤答 {c!r} が包含関係にあります。"))

    conf = q.get("confidence")
    if conf not in ALLOWED_CONFIDENCE:
        issues.append(Issue("ERROR", qid, "confidence",
                            f"confidence は {sorted(ALLOWED_CONFIDENCE)} のみ許可されます"
                            f"（現在 {conf!r}）。C 以下は UNVERIFIED.md へ。"))

    sources = q.get("sources")
    if not isinstance(sources, list) or not sources:
        issues.append(Issue("ERROR", qid, "sources", "出典が1件もありません。"))
    else:
        for s in sources:
            if not isinstance(s, str) or not URL_RE.match(s):
                issues.append(Issue("ERROR", qid, "sources",
                                    f"出典が http(s) の URL ではありません: {s!r}"))
        # 事実は収集時に複数ソースで突き合わせているが、URL として記録できているのが
        # 1件だけの問題が残っている。読み手が独力で裏を取れるよう2件目を足したい。
        if len(sources) == 1:
            try:
                num = int(str(q.get("id", "")).split("-")[1])
            except (IndexError, ValueError):
                num = SOURCE_GATE_FROM  # id が読めないものは新規扱いで厳しく見る
            if num >= SOURCE_GATE_FROM:
                issues.append(Issue("ERROR", qid, "sources/single",
                                    f"出典URLが1件だけです。conan-{SOURCE_GATE_FROM:03d} 以降は"
                                    "2件以上が必須です（ダブルチェックの記録）。"))
            else:
                issues.append(Issue("WARN", qid, "sources/single",
                                    "出典URLが1件だけです。2件目を追記できると理想的です。"))

    if q.get("volatile"):
        if not q.get("asOf"):
            issues.append(Issue("ERROR", qid, "volatile",
                                "volatile:true なのに asOf がありません。"))
    else:
        # 時点表現が本文にあるのに volatile が立っていないケースを拾う
        text = q.get("question", "")
        if "時点" in text:
            issues.append(Issue("WARN", qid, "volatile",
                                "問題文に「時点」を含みますが volatile が立っていません。"))


def check_meta(doc: dict, questions: list[dict], issues: list[Issue]) -> None:
    meta = doc.get("meta") or {}

    if meta.get("total") != len(questions):
        issues.append(Issue("ERROR", "meta", "meta/total",
                            f"meta.total={meta.get('total')} が実データ {len(questions)} 問と一致しません。"))

    actual_diff = Counter(q.get("difficulty") for q in questions)
    if dict(actual_diff) != (meta.get("countsByDifficulty") or {}):
        issues.append(Issue("ERROR", "meta", "meta/countsByDifficulty",
                            f"難易度別の集計が一致しません。実データ: {dict(actual_diff)}"))

    actual_cat = Counter(q.get("category") for q in questions)
    if dict(actual_cat) != (meta.get("countsByCategory") or {}):
        issues.append(Issue("ERROR", "meta", "meta/countsByCategory",
                            f"カテゴリ別の集計が一致しません。実データ: {dict(actual_cat)}"))


def check_global(questions: list[dict], issues: list[Issue]) -> None:
    ids = [q.get("id") for q in questions]
    for qid, n in Counter(ids).items():
        if n > 1:
            issues.append(Issue("ERROR", str(qid), "id/duplicate", f"id が {n} 回使われています。"))

    texts = [q.get("question") for q in questions]
    for text, n in Counter(texts).items():
        if n > 1:
            issues.append(Issue("ERROR", str(text)[:40], "question/duplicate",
                                f"同じ問題文が {n} 問あります。"))

    # ランダム出題したときに「いつも同じ位置が正解」にならないかを確認する
    total = len(questions)
    if total:
        pos = Counter(q.get("answerIndex") for q in questions)
        for i in range(CHOICE_COUNT):
            ratio = pos.get(i, 0) / total
            if abs(ratio - 1 / CHOICE_COUNT) > POSITION_BIAS_TOLERANCE:
                issues.append(Issue("WARN", f"position {i}", "answer/bias",
                                    f"正解が位置 {i} に {ratio:.0%} 偏っています"
                                    f"（理想 {1/CHOICE_COUNT:.0%}）。出題時のシャッフルを推奨。"))


def check_rendered_md(issues: list[Issue]) -> None:
    """quiz-bank.md が questions.json と同期しているかを検査する。"""
    md_path = REPO_ROOT / "docs" / "quiz-bank.md"
    if not md_path.exists():
        issues.append(Issue("ERROR", "quiz-bank.md", "render", "quiz-bank.md がありません。"))
        return
    try:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import render_quiz  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - 環境依存
        issues.append(Issue("WARN", "quiz-bank.md", "render",
                            f"render_quiz を読み込めず同期を確認できません: {exc}"))
        return
    doc = json.loads((REPO_ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
    if render_quiz.render(doc) != md_path.read_text(encoding="utf-8"):
        issues.append(Issue("ERROR", "quiz-bank.md", "render",
                            "quiz-bank.md が questions.json と一致しません。"
                            "`python3 scripts/render_quiz.py` で再生成してください。"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="名探偵コナン クイズデータの機械的検査")
    parser.add_argument("--path", default=str(DATA_PATH), help="検査する questions.json のパス")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力する")
    parser.add_argument("--strict", action="store_true", help="WARN も失敗扱いにする")
    args = parser.parse_args(argv)

    issues: list[Issue] = []
    doc = load(Path(args.path), issues)

    questions: list[dict] = []
    if doc is not None:
        questions = doc.get("questions") or []
        if not isinstance(questions, list) or not questions:
            issues.append(Issue("ERROR", "questions", "questions", "questions が空です。"))
        else:
            meta = doc.get("meta") or {}
            diffs = {d.get("key") for d in (meta.get("difficulties") or [])}
            cats = {c.get("key") for c in (meta.get("categories") or [])}
            if not diffs:
                issues.append(Issue("ERROR", "meta", "meta/difficulties", "difficulties が未定義です。"))
            if not cats:
                issues.append(Issue("ERROR", "meta", "meta/categories", "categories が未定義です。"))
            for idx, q in enumerate(questions, 1):
                check_question(q, idx, diffs, cats, issues)
            check_global(questions, issues)
            check_meta(doc, questions, issues)
            if Path(args.path) == DATA_PATH:
                check_rendered_md(issues)

    errors = [i for i in issues if i.severity == "ERROR"]
    warns = [i for i in issues if i.severity == "WARN"]

    if args.json:
        print(json.dumps({
            "path": args.path,
            "questions": len(questions),
            "errors": len(errors),
            "warnings": len(warns),
            "issues": [i.as_dict() for i in issues],
        }, ensure_ascii=False, indent=2))
    else:
        for issue in issues:
            print(issue)
        by_diff = Counter(q.get("difficulty") for q in questions)
        summary = " / ".join(f"{k}:{v}" for k, v in sorted(by_diff.items()))
        print(f"\n検査対象: {len(questions)} 問（{summary}）")
        if questions:
            multi = sum(1 for q in questions if len(q.get("sources") or []) >= 2)
            print(f"出典URL 2件以上: {multi} / {len(questions)} 問")
        print(f"ERROR {len(errors)} 件、WARN {len(warns)} 件")
        if not errors and not warns:
            print("問題なし。")

    if errors:
        return 1
    if warns and args.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
