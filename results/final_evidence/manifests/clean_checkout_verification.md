# P8 — Clean-checkout / remanifest verification

## Commands (separate)

```bash
# 1) Generate (writes reports then hashes; excludes manifest from inventory)
python scripts/final_evidence/executable_validation.py

# 2) Verify read-only (must FAIL on any change/missing file)
python scripts/final_evidence/verify_release_manifest.py
```

## This run

- Artifacts listed: **301**
- Failures: **0**
- Passed: **True**

`.gitattributes` enforces `eol=lf` for scientific text artifacts to reduce Windows CRLF vs Git LF size mismatches.

If verifying from a fresh clone: checkout the freeze commit, run only the verify command against the committed manifest (do not regenerate first).
