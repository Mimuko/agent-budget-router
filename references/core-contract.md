# ABR Core 契約

> Status: Normative / Skill v1 design
>
> ABR Coreはpromptと正規化済み`task_context`からTaskEstimateを一度生成し、任意の正規化済み`budget_context`と組み合わせて最終推奨を返す純粋な判定層である。
> 共通I/Oは`io-contract.md`、workflowと呼び出し順は`skill-contract.md`を正とする。

## 責務境界

CoreはHost、Provider、Resolver、UI、Agent起動方法、credential、外部API、外部接続、永続化を知らない。
budget_contextの取得・正規化・永続化はCore外の責務である。Coreは外部から渡されたsnapshotを
判定材料としてのみ使う。入力の欠落や参照解決状態のpolicy mappingはOrchestratorが扱う。
Coreは受け取った作業文脈からpreflight要否と見積・予算上の推奨を返す。

## API

```text
should_preflight(prompt, task_context?) -> PreflightCheck
estimate_task(prompt, task_context?) -> TaskEstimate
route(task_estimate, budget_context?) -> RouteResult
```

`should_preflight`と`estimate_task`では`prompt`が必須である。空または契約上利用できないpromptは
`should_preflight`が`INPUT_UNAVAILABLE`と判定し、`estimate_task`へ渡さない。
`task_context`はoptionalであり、未提供は有効な入力である。提供された場合は契約に沿った
正規化済み構造でなければならず、不正な値は入力検証エラーとする。外部参照がないこと
（`NO_REFERENCE`）自体はエラーではない。

3つのAPIは副作用を持たず、同じ引数と同じ契約/catalog versionに対して同じ結果を返す。
`should_preflight`は軽量判定のみを行い、詳細見積、履歴処理、budget snapshot取得、Host状態照会、
見積記録の保存を行わない。結果は次のいずれかとする。

```json
{"decision":"SKIP|PREFLIGHT|INPUT_UNAVAILABLE","reason":"stable_reason_code"}
```

`should_preflight`が`PREFLIGHT`を返した場合だけ`estimate_task`を一度呼び、その結果を`route`と
Budget Cost Estimatorの両方へ渡す。`estimate_task`は既存の見積ロジックとcatalogを再利用する。
参照情報は受け取らず、見積に必要な`title`、`summary`、`acceptance_criteria`、
`path_hints`のみを`task_context`から読む。`source_identity`はCoreへ渡さない。

### TaskEstimate

```json
{
  "task_class": "feature_build",
  "estimated_context": {"min": 42000, "max": 184000},
  "estimated_generation": {"min": 8000, "max": 25000},
  "base_recommendation": "DIRECT",
  "base_reason": "stable_reason_code"
}
```

`task_class`は`small_edit | feature_build | repository_review | cross_cutting | large_refactor`とする。
`estimated_context`と`estimated_generation`はそれぞれ非負の整数で`min <= max`を満たす。
`base_recommendation`はタスク規模・複雑度のみから得る`DIRECT | SPLIT | DEFER`で、現在の
利用枠snapshotを反映しない。`base_reason`はその判定理由の非空の安定コードである。TaskEstimateは
同一評価中のtask sizingのSingle Source of Truthとし、Orchestratorも`route`も見積を再実行しない。
TaskEstimateにbudget_contextやsource_identityは含めず、同一評価内で変更しない。

`route`は受け取ったTaskEstimateを検証し、同じ見積値を変更せずSkill v1の`preflight` objectへ
引き継ぐ。任意のbudget_contextとbase recommendationを統合して最終`recommended_policy`を返す。
promptやtask_contextを再取得せず、task sizingも実行しない。
具体的な比率と閾値は`budget-policy.md`を正とする。

### budget_context

`budget_context`はCore外で取得・正規化された利用枠snapshotと今回タスクの予測消費率であり、
Provider固有API responseを含めない。今回タスクの消費率はBudget Cost Estimatorが生成する。
取得元snapshotまたは消費率を用意できない場合は省略できる。Coreは受け取った比率を読み取り専用の
判定材料として使い、自ら利用枠を問い合わせたり、token数へ換算したり、保存したりしない。

```json
{
  "remaining_ratio": 0.63,
  "estimated_task_ratio": 0.08,
  "snapshot_at": "2026-09-24T02:00:00Z",
  "scope": "account"
}
```

- `remaining_ratio`: 必須のnumber。対象scope・quota window・総量基準の残利用率で、`0.0 <= x <= 1.0`。
- `estimated_task_ratio`: 必須のnumber。Budget Cost Estimatorが同じscope・quota window・総量基準に対して算出した今回タスクの予測消費率。有限値の`0.0 <= x`。`1.0`超も利用枠総量を超える見積として許可する。
- `snapshot_at`: 必須のISO-8601/RFC 3339 timestamp。UTC offsetを含める。
- `scope`: 必須のHost/Provider非依存文字列。例は`account`、`workspace`、`project`。取得元の固有IDやraw responseは含めない。

Budget Cost Estimator / normalizerは、両比率が同一scope・同一quota window・同一総量基準に対する
値であることを保証できる場合だけbudget_contextを生成する。保証できない場合や消費率の根拠が
ない場合は省略する。Coreは受け取った正規化済みbudget_contextの型・値域のみを検証し、
quota windowや総量基準を外部情報と照合しない。snapshotの鮮度判断に現在時刻は使わず、
呼び出し側が判定に適さないsnapshotを省略する。省略時はTaskEstimateのbase recommendationを
そのまま返す。CoreはBudget Cost Estimator、履歴、calibrationを参照しない。

```json
{
  "task_class":"feature_build",
  "estimated_context":{"min":42000,"max":184000},
  "estimated_generation":{"min":8000,"max":25000},
  "base_recommendation":"DIRECT",
  "base_reason":"stable_reason_code",
  "recommended_policy":"DIRECT|SPLIT|DEFER",
  "recommendation_reason":"stable_reason_code"
}
```

`base_reason`はTaskEstimate由来のtask sizing理由、`recommendation_reason`は`route()`が返す
最終`recommended_policy`の理由である。budget recommendationがbaseより慎重な場合は
`budget_limited`、`budget_exceeded`、`budget_exhausted`の該当コードを返す。budget_contextが
未提供なら`budget_unavailable`を返し、task sizingの根拠は`base_reason`に保持する。
budget recommendationがbase以下の場合は`base_reason`を最終理由とする。
共通I/Oのトップレベル`reason`は`should_preflight`またはworkflowの理由であり、Coreの
`recommendation_reason`を上書きしない。

`recommended_policy`はタスク・見積・任意のbudget_contextに基づくCoreの推奨であり、
`execution_policy`はworkflow上の実際の扱いである。Skill v1出力ではCore結果を`preflight`内に
保持し、Orchestratorが別フィールドの`execution_policy`、`state`、`forward.allowed`を管理する。
`CONFIRM_FIRST`はworkflow状態であり、Coreの`recommended_policy`には含めない。

- `DIRECT`はworkflow上`CONFIRM_FIRST`で包めるが、Coreの推奨値を変更しない。
- `SPLIT`は承認だけで`DIRECT`に変換しない。
- `DEFER`は承認だけで`READY`に変換しない。

## 見積互換層

既存`estimate()`の出力語彙はCore内部の互換入力に限る。Skill v1へ出す際は次のように変換し、
旧語彙をOrchestrator、Resolver、共通I/Oへ漏らさない。

| 既存`verdict` | TaskEstimate `base_recommendation` |
|:--|:--|
| `GO` | `DIRECT` |
| `SPLIT_RECOMMENDED` | `SPLIT` |
| `DEFER` | `DEFER` |

catalog、見積式、既存計測データの意味はこの整理だけを理由に変更しない。

## 既存入口との移行

- `should_preflight()`の判定基準を保ち、Host非依存の軽量APIとして維持する。
- `route_preflight()`を`estimate_task()`と`route()`を順に呼ぶ互換wrapperとし、移行中に既存呼び出し元を壊さない。
- `route()`が利用可能になった後も、旧wrapperの削除は別作業とする。
- `estimate()`とCoreの間に互換変換を置き、旧`GO`系語彙を境界外へ出さない。

## 契約上の停止条件

- promptが必須条件を満たさない場合、`should_preflight`は`INPUT_UNAVAILABLE`を返す。
- `task_context`はoptional。省略や外部参照なしはエラーではなく、提供された不正なcontextは入力検証エラーとする。
- 不正なTaskEstimateは`route`の入力検証エラーとし、見積を再実行して補完しない。
- 提供された不正な`budget_context`は入力検証エラーとし、別の値で補完・推測しない。
- Resolverの失敗policy、Host UI、ユーザー承認の可否をCore内で決めない。
- `source_identity`の比較、承認再検証、状態遷移はOrchestratorの責務とする。
