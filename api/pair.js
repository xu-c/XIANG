const defaultEndpoint = "https://wmoaxlrncbfcsyqtfbku.supabase.co/functions/v1/xiang-pair";

module.exports = async (req, res) => {
  res.setHeader("Cache-Control", "no-store");
  if (req.method !== "POST") return res.status(405).json({error: "invalid_request"});
  const origin = req.headers.origin;
  if (origin && origin !== "https://" + req.headers.host && origin !== "http://" + req.headers.host) {
    return res.status(403).json({error: "invalid_request"});
  }
  const body = typeof req.body === "string" ? req.body : JSON.stringify(req.body);
  if (!body || Buffer.byteLength(body) > 12288) {
    return res.status(400).json({error: "invalid_request"});
  }
  try {
    const upstream = await fetch(process.env.XIANG_SIGNAL_URL || defaultEndpoint, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body, signal: AbortSignal.timeout(10000)
    });
    return res.status(upstream.status).json(await upstream.json());
  } catch {
    return res.status(502).json({error: "pair_unavailable"});
  }
};

