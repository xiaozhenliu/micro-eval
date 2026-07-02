# Ledger fixture workspace

This tiny Python workspace is copied into a temporary directory for every
`micro-eval` cell. Agents should fix `ledger.py`; the wrapper runs:

```bash
python -m unittest discover -s tests
```

The copied workspace is disposable. Do not use it for secrets or production data.
