# 06. クイズデータの仕様とアプリでの使い方

クイズアプリからランダム出題するためのデータ仕様です。

- **正本：** [`questions.json`](../data/questions.json)（全120問）
- 閲覧用の [`quiz-bank.md`](./quiz-bank.md) は questions.json から**自動生成**されるビューです。

> 最終更新：2026-09-04

---

## 1. ファイル構造

```jsonc
{
  "meta": {
    "title": "名探偵コナン クイズ問題データ",
    "version": "1.0.0",
    "updated": "2026-09-04",
    "total": 120,
    "countsByDifficulty": { "beginner": 40, "intermediate": 40, "advanced": 40 },
    "countsByCategory":   { "basics": 11, "characters": 50, ... },
    "difficulties": [ { "key": "beginner", "label": "初級" }, ... ],
    "categories":   [ { "key": "basics",   "label": "作品の基本" }, ... ],
    "notes": [ "..." ]
  },
  "questions": [ /* 下記のオブジェクトが120件 */ ]
}
```

## 2. 問題オブジェクトのフィールド

| フィールド | 型 | 説明 |
|---|---|---|
| `id` | string | 安定した一意ID（`conan-001` 形式）。進捗保存や誤答記録のキーに使える |
| `difficulty` | string | `beginner` / `intermediate` / `advanced` |
| `difficultyLabel` | string | 表示用の日本語（`初級` など） |
| `category` | string | `basics` / `characters` / `anime` / `movies` / `music` / `organization` / `gadgets` / `trivia` |
| `categoryLabel` | string | 表示用の日本語（`登場人物` など） |
| `question` | string | 問題文 |
| `choices` | string[] | 選択肢。**必ず4つ**、重複なし |
| `answerIndex` | number | `choices` 内の正解の位置（0始まり） |
| `answer` | string | 正解の文字列（`choices[answerIndex]` と必ず一致） |
| `explanation` | string | 解説。出題後に表示する用 |
| `confidence` | string | `A`＝公式で確認／`B`＝Wikipedia＋独立メディアで一致。**C以下は収録しない** |
| `sources` | string[] | 出典URL（**conan-121 以降は2件以上が必須**。現在458問中403問が2件以上） |
| `volatile` | boolean? | `true` なら時間経過で答えが変わりうる問題 |
| `asOf` | string? | `volatile` が `true` のときの基準日 |

### 難易度の目安

| 難易度 | 想定 | 例 |
|---|---|---|
| `beginner`（初級） | アニメを見たことがあれば答えられる | 作者、主人公の本名、通っている学校 |
| `intermediate`（中級） | ファンなら答えられる | 誕生日、声優、劇場版の公開年、主題歌 |
| `advanced`（上級） | 詳しい人向け | 組織の内情、名前の由来、興行収入の記録 |

---

## 3. ランダム出題の実装例

### JavaScript / TypeScript

```js
const data = await fetch("./questions.json").then((r) => r.json());

// Fisher-Yates シャッフル
const shuffle = (arr) => {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
};

/**
 * 出題セットを作る。
 * @param {object} opts
 * @param {string} [opts.difficulty] 難易度で絞る（省略で全難易度）
 * @param {string} [opts.category]   カテゴリで絞る
 * @param {number} [opts.count]      出題数
 * @param {boolean} [opts.includeVolatile] 時点依存の問題を含めるか
 */
function pickQuestions({ difficulty, category, count = 10, includeVolatile = false } = {}) {
  let pool = data.questions;
  if (difficulty) pool = pool.filter((q) => q.difficulty === difficulty);
  if (category) pool = pool.filter((q) => q.category === category);
  if (!includeVolatile) pool = pool.filter((q) => !q.volatile);

  return shuffle(pool)
    .slice(0, count)
    .map((q) => {
      // 選択肢もシャッフルして、正解の位置が固定されないようにする
      const choices = shuffle(q.choices);
      return { ...q, choices, answerIndex: choices.indexOf(q.answer) };
    });
}

// 例：初級から10問
const quiz = pickQuestions({ difficulty: "beginner", count: 10 });
```

### Python

```python
import json, random

with open("data/questions.json", encoding="utf-8") as f:
    data = json.load(f)

def pick_questions(difficulty=None, category=None, count=10, include_volatile=False):
    pool = data["questions"]
    if difficulty:
        pool = [q for q in pool if q["difficulty"] == difficulty]
    if category:
        pool = [q for q in pool if q["category"] == category]
    if not include_volatile:
        pool = [q for q in pool if not q.get("volatile")]

    picked = random.sample(pool, min(count, len(pool)))
    out = []
    for q in picked:
        choices = random.sample(q["choices"], len(q["choices"]))
        out.append({**q, "choices": choices, "answerIndex": choices.index(q["answer"])})
    return out

quiz = pick_questions(difficulty="advanced", count=10)
```

---

## 4. 実装上の注意

### ⚠️ 選択肢は必ずシャッフルする

データ側でも正解の位置は 0〜3 に均等分散（各30問）させてありますが、
**出題時にもシャッフルしてください**。同じ問題を繰り返し出したときに、
プレイヤーが正解の位置を覚えてしまうのを防ぐためです。

### ⚠️ `volatile` の扱い

`volatile: true` の問題は、時間が経つと正解が変わります（例：興行収入ランキング）。
既定では**出題対象から外す**か、問題文に `asOf` の日付を添えて出してください。
上の実装例は既定で除外しています。

### 重複出題を避ける

1セッション内での重複は `id` で管理してください。
連続プレイでの「さっきも出た」を減らすなら、直近に出題した `id` を保持して
プールから除外する実装が有効です。

### 難易度ミックス

「初級4問＋中級4問＋上級2問」のような構成にするなら、難易度ごとに
`pickQuestions` を呼び、結果を結合してからもう一度シャッフルしてください。

---

## 5. データを更新するときの手順

```bash
# 1. questions.json を編集する（正本）

# 2. 閲覧用の Markdown を再生成する
python3 scripts/render_quiz.py

# 3. 機械的な整合性を検査する
python3 scripts/verify_quiz.py
```

`verify_conan_quiz.py` は次を検査します。

- `id` の重複・書式、問題文の重複
- 選択肢がちょうど4つで重複がないか
- `choices[answerIndex] == answer` か
- `difficulty` / `category` が `meta` の定義と一致するか
- `confidence` が **A / B のみ**か（C以下は `UNVERIFIED.md` 行き）
- 出典が1件以上あり http(s) URL か
- `meta` の集計値が実データと一致するか
- 正解位置に偏りがないか
- 正解が誤答の部分文字列になっていないか（消去法で当たる問題の検出）
- `quiz-bank.md` が `questions.json` と同期しているか

**新しい問題を追加するときは、必ず2系統以上の独立した情報源で裏を取り、
`sources` に両方のURLを入れてください。** 1系統しか見つからない事実は
`confidence: "C"` 相当なので、`UNVERIFIED.md` に記録して収録を見送ります。

なお初期に作った55問（conan-120 以前）は、照合はしたものの `sources` に記録できた
URLが1件だけです。`verify_conan_quiz.py` がこれを WARN として列挙するので、
2件目を追記していくバックログとして使えます（WARN は出題を止めません）。
**conan-121 以降は2件必須**で、1件だと ERROR になります。
