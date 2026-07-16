/* =====================================================================
 *  API adapter - one interface, two backends.
 *  The UI only ever calls Api.claim(name) and Api.submit(name, pairId, answers).
 *
 *    claim(name)                -> { pairs: [{pair_id, image_a, image_b, province, year}], remaining }
 *    submit(name, pairId, ans)  -> { ok: true } | { ok: false, reason: "pair_full" | ... }
 *
 *  Both shapes are identical whether the data comes from the local Python
 *  server or from Supabase RPC, so the UI never has to care.
 * ===================================================================== */
const Api = (() => {
  const cfg = window.STUDY_CONFIG;

  async function postJSON(url, body) {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).error || ""; } catch (_) {}
      throw new Error(`${res.status} ${detail}`);
    }
    return res.json();
  }

  async function getJSON(url) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`${res.status}`);
    return res.json();
  }

  /* ---------- LOCAL (Python app.py) ---------- */
  const local = {
    claim: (name) => postJSON("/api/claim", { name, size: cfg.batchSize }),
    submit: (name, pairId, answers, meta) =>
      postJSON("/api/submit", { name, pair_id: pairId, answers, meta }),
    progress: () => getJSON("/api/progress"),
  };

  /* ---------- SUPABASE (production) ----------
   * Lazily loads supabase-js from a CDN (no build step). Calls two SQL
   * functions defined in supabase/schema.sql:
   *   claim_batch(p_name, p_size)        returns json {pairs, remaining}
   *   submit_response(p_pair_id, p_name, p_answers) returns json {ok, reason}
   */
  let _client = null;
  async function client() {
    if (_client) return _client;
    if (!cfg.supabaseUrl || !cfg.supabaseAnonKey) {
      throw new Error("Supabase URL / anon key not set in config.js");
    }
    const { createClient } = await import("https://esm.sh/@supabase/supabase-js@2");
    _client = createClient(cfg.supabaseUrl, cfg.supabaseAnonKey);
    return _client;
  }
  const supabase = {
    claim: async (name) => {
      const c = await client();
      const { data, error } = await c.rpc("claim_batch", { p_name: name, p_size: cfg.batchSize });
      if (error) throw new Error(error.message);
      return data;
    },
    submit: async (name, pairId, answers, meta) => {
      const c = await client();
      // the client IP is added server-side inside submit_response() — the browser
      // cannot read its own public IP.
      const { data, error } = await c.rpc("submit_response", {
        p_pair_id: pairId, p_name: name, p_answers: answers, p_meta: meta || {} });
      if (error) throw new Error(error.message);
      return data;
    },
    progress: async () => {
      const c = await client();
      const { data, error } = await c.rpc("study_progress");
      if (error) throw new Error(error.message);
      return data;
    },
  };

  return cfg.backend === "supabase" ? supabase : local;
})();
