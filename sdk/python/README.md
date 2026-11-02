# echobrief (Python)

Official Python SDK and CLI for the [EchoBrief](https://echobrief.onrender.com) agent API.

## Install / publish

Shipped in-repo. Publishing to PyPI is optional.

```bash
cd sdk/python
python -m pip install -e .
# optional publish (requires credentials)
python -m build && python -m twine upload dist/*
```

## CLI

```bash
echobrief summarize <url> --type ts --cache-only
echobrief health
echobrief job <job_id> --wait
echobrief sandbox
```

`ECHOBRIEF_BASE_URL` defaults to `https://echobrief-backend.onrender.com`.

## SDK

```python
from echobrief import EchoBriefClient

with EchoBriefClient() as client:
    result = client.summarize(
        "https://podcasts.apple.com/...",
        "ts",
        idempotency_key="run-1",
        cache_only=False,
    )
```
