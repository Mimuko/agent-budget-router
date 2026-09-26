# ABR Core 予算判定ポリシー

> Status: Normative / Skill v1 design
>
> 本書は `route(TaskEstimate, budget_context?)` が `DIRECT / SPLIT / DEFER` を決める規則を定義する。
> Core API・出力契約は `core-contract.md`、見積値の意味は `estimation-rules.md` を正とする。
> 本書はSkill v1の予算判定正本である。

## 1. 判定の原則

- タスク規模推定と利用枠消費率推定を別レイヤーとして扱う。
- `estimated_context` と `estimated_generation` はタスク規模・複雑度を表すtoken推定値であり、利用枠消費率そのものではない。
- Coreは正規化済み `budget_context` を純粋な判定材料としてのみ扱う。取得、正規化、校正、永続化はCore外の責務とする。
- `estimate_task`は同じprompt・task_context・契約/catalog versionに同じTaskEstimateを返し、`route`は同じTaskEstimate・budget_contextに同じ結果を返す。
- Core推奨値は `DIRECT | SPLIT | DEFER`。`CONFIRM_FIRST` とworkflow状態はOrchestratorの責務とする。
- budget_contextが未提供なら、利用可能枠を推測せずタスク見積だけによる既存v1判定へfallbackする。
- Coreは履歴、現在時刻、動的閾値を参照しない。

## 2. 正規化済みbudget_context

Codex等から実際に取得できる「アカウント全体の使用率 / 残利用率」を使用し、残利用率からtoken数を逆算しない。Provider固有のquota単位やraw API responseをCoreへ渡さない。

```json
{
  "remaining_ratio": 0.63,
  "estimated_task_ratio": 0.08,
  "snapshot_at": "2026-09-24T02:00:00Z",
  "scope": "account"
}
```

| field | 要件 |
|:--|:--|
| `remaining_ratio` | 必須。対象scope・quota window・総量基準に対する残利用率。有限値で`0.0 <= x <= 1.0`。 |
| `estimated_task_ratio` | 必須。今回タスクが同じscope・quota window・総量基準で消費すると予測する比率。有限値で`0.0 <= x`。上限は設けず、`1.0`超は利用枠総量を超える消費見積を表す有効値。 |
| `snapshot_at` | 必須。UTC offsetを含むISO-8601/RFC 3339 timestamp。Coreは現在時刻との比較に使わない。 |
| `scope` | 必須。Host・Provider非依存のscope名。例: `account`、`workspace`、`project`。取得元固有IDやraw responseを含めない。 |

Budget Cost Estimator / normalizerは、`remaining_ratio` と `estimated_task_ratio` が同一scope・同一quota window・同一総量基準で算出されたことを保証できる場合だけbudget_contextを生成する。保証できない場合や今回タスクの消費率を根拠をもって推定できない場合は省略し、CoreはTaskEstimateのbase recommendationへfallbackする。Coreは正規化済みbudget_contextの型・値域だけを検証し、quota windowや総量基準を外部情報で照合しない。型・値域の違反は入力検証エラーとし、黙って補完しない。

## 3. estimated_task_ratio の責務境界

`estimated_task_ratio` はABR Coreの外にあるBudget Cost Estimator / normalizerが、`estimate_task()`の返すTaskEstimateを受け取って算出する。Estimatorは利用可能な範囲で以下を材料にできる。

- `task_class`
- `estimated_context`、`estimated_generation`
- 同一scope・同一利用枠期間で観測したタスク前後の利用率差
- 将来追加されるcalibration data

Estimatorはtoken規模推定を利用率消費推定へ写像する。estimated_task_ratioを根拠なく補完・推測してはならない。十分なcalibrationまたは決定的な変換根拠がない場合は `budget_context` を省略する。v1では誤った精密さよりbase recommendationへのfallbackを優先する。CoreはEstimatorの内部式、履歴取得、calibration参照、snapshot取得を行わず、渡された比率だけを判定する。Estimator固有の推定式は本v1契約では固定しない。

`should_preflight()`が`PREFLIGHT`を返した場合、Orchestratorは`estimate_task()`を一度だけ実行する。そのTaskEstimateをEstimatorに渡し、必要なbudget_contextを構築した後、同じTaskEstimateを`route()`へ渡す。Orchestratorや`route()`はtask sizingを再実行しない。TaskEstimateは両者に共通するSingle Source of Truthである。

v1の最小schemaにはconfidenceやcalibration versionを含めない。将来、品質評価や再現性記録が必要になった場合はEstimator側のmetadataとして別途定義し、Coreの判定は正規化済み比率を入力とするpure functionに保つ。

## 4. 比較指標

Coreは次の `budget_pressure` を計算する。

```text
budget_pressure = estimated_task_ratio / remaining_ratio
```

例: `remaining_ratio = 0.63`、`estimated_task_ratio = 0.08` の場合、`budget_pressure ≈ 0.127`。
タスク消費率 ÷ 残利用率を使うため、値が大きいほど今回タスクが残枠を多く占める。1.0を超えると今回の推定消費率が残利用率を上回る。

`remaining_ratio == 0` は除算せず、必ず `DEFER` とする。正の残利用率には次の決定表を適用する。

## 5. 予算判定の決定表

| 条件 | Budget recommendation | 解釈 |
|:--|:--|:--|
| `budget_context` 未提供 | 予算判定なし | タスク見積のみのrecommendationへfallback |
| `remaining_ratio == 0` | `DEFER` | 利用可能枠なし |
| `budget_pressure <= 0.50` | `DIRECT` | 推定消費が残利用率の半分以下 |
| `0.50 < budget_pressure <= 1.00` | `SPLIT` | 残枠内の見込みだが余裕が半分未満。段階実行し、呼び出し元が再評価する |
| `budget_pressure > 1.00` | `DEFER` | 推定消費が残利用率を超える |

境界値ちょうど `0.50` は `DIRECT`、ちょうど `1.00` は `SPLIT`、1.00を超えると `DEFER` とする。極端に少ない残利用率にも別の絶対値閾値は設けず、同じ比率式を使う。
閾値との比較には丸め前の比率を使い、表示用の丸め値で判定結果を変えない。

`SPLIT`は総消費量が減る保証ではない。呼び出し元Agentがタスクを段階化し、各段階で利用可能枠を再確認するための推奨である。Coreは分割計画を生成せず、後続段階の予算を予約・保証しない。

## 6. タスク見積と予算推奨の統合

`estimate_task()`が既存タスク見積をTaskEstimateの`base_recommendation`と`base_reason`へ変換する。既存語彙との互換写像は以下のとおり。

| 既存見積 `verdict` | Base recommendation |
|:--|:--|
| `GO` | `DIRECT` |
| `SPLIT_RECOMMENDED` | `SPLIT` |
| `DEFER` | `DEFER` |

`route()`はTaskEstimateの`base_recommendation`を受け取り、budget_contextがある場合は決定表からbudget recommendationを得て、より保守的な方を最終`recommended_policy`とする。

```text
DIRECT < SPLIT < DEFER
final recommendation = max(base recommendation, budget recommendation)
```

予算に余裕があってもbase recommendationを弱めず、予算が逼迫している場合はbaseより慎重な方へ引き上げる。budget_context未提供時はbase recommendationをそのまま返す。

## 7. 代表ケース

| # | base | remaining_ratio | estimated_task_ratio | pressure | 結果 | 理由 |
|--:|:--|--:|--:|--:|:--|:--|
| 1 | `DIRECT` | — | — | — | `DIRECT` | budget_contextなし。baseへfallback |
| 2 | `DIRECT` | 0.63 | 0.08 | 約0.127 | `DIRECT` | 残利用率63%、推定消費8% |
| 3 | `DIRECT` | 0.50 | 0.25 | 0.50 | `DIRECT` | 下側境界ちょうど |
| 4 | `DIRECT` | 0.50 | 0.2501 | 0.5002 | `SPLIT` | 0.50をわずかに超える |
| 5 | `DIRECT` | 0.40 | 0.40 | 1.00 | `SPLIT` | 推定消費率と残利用率が同値 |
| 6 | `DIRECT` | 0.40 | 0.4001 | 1.00025 | `DEFER` | 推定消費率が残利用率を超える |
| 7 | `DIRECT` | 0 | 0.01 | — | `DEFER` | 残利用率ゼロ |
| 8 | `SPLIT` | 0.80 | 0.05 | 0.0625 | `SPLIT` | 予算に余裕があってもbase推奨を維持 |
| 9 | `DEFER` | 0.95 | 0.01 | 約0.011 | `DEFER` | 予算に余裕があってもbase推奨を維持 |

## 8. 出力と理由コード

予算判定の結果はCoreの `preflight.recommended_policy` に統合する。`task_class`、見積レンジ、`base_recommendation`、`base_reason`は渡されたTaskEstimateから変更せず引き継ぐ。`preflight.recommendation_reason`は最終推奨の理由を表す。budget recommendationがbaseより慎重なら該当budget理由コード、budget_context未提供なら`budget_unavailable`、budget recommendationがbase以下なら`base_reason`を返す。`execution_policy`、`state`、確認要求はOrchestrator / Skill v1 workflow契約に従い、`CONFIRM_FIRST`をCore推奨に含めない。

実装時に予算由来の理由を識別する場合、以下の安定reason codeを使う。

- `budget_unavailable` — budget_contextなし。base recommendationを使用。
- `budget_roomy` — pressure `<= 0.50`。
- `budget_limited` — pressure `> 0.50` かつ `<= 1.00`。
- `budget_exceeded` — pressure `> 1.00`。
- `budget_exhausted` — remaining_ratioが0。

reasonは推奨の根拠であり、workflow policyやapproval stateを意味しない。

## 9. calibration data の将来接続

calibrationは将来、CoreではなくBudget Cost Estimatorへ接続する。実行前後の同一scope・同一期間の利用率snapshotからタスクに帰属可能な実測利用率差を得て、`task_class`、`estimated_context`、`estimated_generation`と関連づける。Estimatorは校正データを用いて次回の `estimated_task_ratio` を生成し、Coreへ本書のschemaで渡す。

並行実行等により実測差をタスクへ帰属できない場合は校正サンプルに使わない。推定できない場合は `budget_context` を省略し、Coreはbase recommendationへfallbackする。校正データの保存・集計・version管理、confidence判定、推定式、最低サンプル数、scope一致条件はEstimatorの別契約で定める。v1 Coreは履歴を参照しない。
