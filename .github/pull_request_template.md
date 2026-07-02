## Summary

## Scope

- [ ] CLI/runtime
- [ ] Local service/debug console
- [ ] Docs
- [ ] Tests
- [ ] Other:

## Verification

```bash
python3 -m unittest discover -s skills/loop-engine/tests -p 'test_*.py'
git diff --check
```

## Privacy Check

- [ ] No `.roundtable/sessions/**` content committed
- [ ] No tokens, credentials, private memory, or raw provider logs committed
- [ ] Public wording treats the current release as a tool preview, not a finished product
