const DEFAULT_BASE = "https://echobrief-backend.onrender.com";

function joinUrl(base, path) {
  return `${base.replace(/\/$/, "")}${path.startsWith("/") ? path : `/${path}`}`;
}

export class EchoBriefClient {
  /**
   * @param {{ baseUrl?: string, fetchImpl?: typeof fetch }} [options]
   */
  constructor(options = {}) {
    this.baseUrl = options.baseUrl || process.env.ECHOBRIEF_BASE_URL || DEFAULT_BASE;
    this.fetchImpl = options.fetchImpl || globalThis.fetch;
    if (!this.fetchImpl) {
      throw new Error("fetch is required (Node 18+ or provide fetchImpl)");
    }
  }

  async request(method, path, { body, headers, query } = {}) {
    const url = new URL(joinUrl(this.baseUrl, path));
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null) url.searchParams.set(key, String(value));
      }
    }
    const response = await this.fetchImpl(url, {
      method,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...headers,
      },
      body: body ? JSON.stringify(body) : undefined,
    });
    const text = await response.text();
    let data = null;
    try {
      data = text ? JSON.parse(text) : null;
    } catch {
      data = { raw: text };
    }
    return { ok: response.ok, status: response.status, data, headers: response.headers };
  }

  health() {
    return this.request("GET", "/health");
  }

  capabilities() {
    return this.request("GET", "/.well-known/echobrief/capabilities.json");
  }

  sandbox() {
    return this.request("GET", "/agent/v1/sandbox");
  }

  /**
   * @param {{ url: string, summaryType?: string, idempotencyKey?: string, cacheOnly?: boolean }} input
   */
  summarize({ url, summaryType = "ts", idempotencyKey, cacheOnly = false }) {
    const headers = {};
    if (idempotencyKey) headers["Idempotency-Key"] = idempotencyKey;
    if (cacheOnly) headers["X-EchoBrief-Cache-Only"] = "true";
    return this.request("POST", "/agent/v1/episodes/summaries", {
      body: { url, summary_type: summaryType, ...(cacheOnly ? { cache_only: true } : {}) },
      headers,
      query: cacheOnly ? { cache_only: "true" } : undefined,
    });
  }

  getJob(jobId) {
    return this.request("GET", `/agent/v1/jobs/${encodeURIComponent(jobId)}`);
  }

  getSummary({ platform, episodeId, summaryType }) {
    return this.request("GET", "/agent/v1/summaries", {
      query: { platform, episode_id: episodeId, summary_type: summaryType },
    });
  }

  /**
   * Poll until terminal or timeout.
   * @param {string} jobId
   * @param {{ intervalMs?: number, timeoutMs?: number }} [options]
   */
  async waitForJob(jobId, { intervalMs = 2000, timeoutMs = 240000 } = {}) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
      const result = await this.getJob(jobId);
      const status = result.data?.status;
      if (["done", "failed", "cancelled", "expired"].includes(status)) {
        return result;
      }
      await new Promise((r) => setTimeout(r, intervalMs));
    }
    throw new Error(`Timed out waiting for job ${jobId}`);
  }
}

export { DEFAULT_BASE };
