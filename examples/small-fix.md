# Example: small fix

Fix a typo in `mimu-core/README.md` line 42. Single file, no architecture changes.

## Expected output

- **Verdict:** GO
- **Complexity:** LOW
- **Pattern:** single-file edit
- **Lane:** auto-lane

## Run

```bash
python scripts/estimate.py "Fix typo in mimu-core/README.md line 42" \
  --path-hint mimu-core/README.md
```
