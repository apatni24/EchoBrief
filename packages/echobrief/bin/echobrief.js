#!/usr/bin/env node
import { EchoBriefClient } from "../src/index.js";

function usage() {
  console.log(`Usage:
  echobrief summarize <url> [--type bs|ns|ts] [--cache-only] [--idempotency-key <key>] [--wait]
  echobrief health
  echobrief job <job_id>
  echobrief sandbox

Env:
  ECHOBRIEF_BASE_URL   default https://echobrief-backend.onrender.com
`);
}

function parseArgs(argv) {
  const args = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (token === "--type") args.type = argv[++i];
    else if (token === "--cache-only") args.cacheOnly = true;
    else if (token === "--idempotency-key") args.idempotencyKey = argv[++i];
    else if (token === "--wait") args.wait = true;
    else if (token === "--help" || token === "-h") args.help = true;
    else args._.push(token);
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help || args._.length === 0) {
    usage();
    process.exit(args.help ? 0 : 1);
  }
  const client = new EchoBriefClient();
  const [cmd, ...rest] = args._;

  if (cmd === "health") {
    const res = await client.health();
    console.log(JSON.stringify(res.data, null, 2));
    process.exit(res.ok ? 0 : 1);
  }

  if (cmd === "sandbox") {
    const res = await client.sandbox();
    console.log(JSON.stringify(res.data, null, 2));
    process.exit(res.ok ? 0 : 1);
  }

  if (cmd === "job") {
    const jobId = rest[0];
    if (!jobId) {
      usage();
      process.exit(1);
    }
    const res = args.wait ? await client.waitForJob(jobId) : await client.getJob(jobId);
    console.log(JSON.stringify(res.data, null, 2));
    process.exit(res.ok ? 0 : 1);
  }

  if (cmd === "summarize") {
    const url = rest[0];
    if (!url) {
      usage();
      process.exit(1);
    }
    let res = await client.summarize({
      url,
      summaryType: args.type || "ts",
      idempotencyKey: args.idempotencyKey,
      cacheOnly: !!args.cacheOnly,
    });
    if (args.wait && res.data?.job_id && !["done", "failed", "cancelled", "expired"].includes(res.data.status)) {
      res = await client.waitForJob(res.data.job_id);
    }
    console.log(JSON.stringify(res.data, null, 2));
    process.exit(res.ok || res.status === 202 ? 0 : 1);
  }

  usage();
  process.exit(1);
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
