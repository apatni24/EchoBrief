# echobrief

Official JavaScript SDK and CLI for the [EchoBrief](https://echobrief.onrender.com) agent API.

## Install / publish

This package is shipped in-repo. Publishing to npm is optional and not required for the backend deploy.

```bash
# from repo root
cd packages/echobrief
npm publish --access public   # requires npm credentials
```

Local use without publishing:

```bash
node packages/echobrief/bin/echobrief.js summarize "https://podcasts.apple.com/..." --type ts
# or
npm link   # inside packages/echobrief
echobrief summarize "<url>"
```

## CLI

```bash
echobrief summarize <url> [--type bs|ns|ts] [--cache-only] [--idempotency-key <key>] [--wait]
echobrief health
echobrief job <job_id>
echobrief sandbox
```

`ECHOBRIEF_BASE_URL` defaults to `https://echobrief-backend.onrender.com`.

## SDK

```js
import { EchoBriefClient } from "echobrief";

const client = new EchoBriefClient();
const { data } = await client.summarize({
  url: "https://podcasts.apple.com/...",
  summaryType: "ts",
  idempotencyKey: "run-1",
});
```

Production is shared. Prefer `--cache-only` / `getSummary` for dry reads.
