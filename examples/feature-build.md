# Example: feature build

Add a new validation step to the existing `docs-sheets-sync` skill manifest check.
Known module area, 3–5 files, clear acceptance criteria.

## Expected output

- **Verdict:** GO
- **Complexity:** MEDIUM
- **Pattern:** known feature area
- **Lane:** implementer (Composer 2.5, speed=fast)

## Run

```bash
python scripts/estimate.py \
  "Add validation for empty owned_columns in docs-sheets-sync manifest" \
  --path-hint mimu-core/skills/docs-sheets-sync/
```
