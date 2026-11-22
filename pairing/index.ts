const origins = new Set(["https://xiangzero.vercel.app"]);
const base = Deno.env.get("SUPABASE_URL")! + "/rest/v1/";
const credential = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/;

function validDescription(value: unknown): value is string {
  return typeof value === "string" && value.length <= 8192 && value.startsWith("v=0") &&
    value.includes("m=application ");
}

function newCode() {
  const [high, low] = crypto.getRandomValues(new Uint32Array(2));
  return ((BigInt(high) * 4294967296n + BigInt(low)) % 1000000n)
    .toString().padStart(6, "0");
}

async function database(path: string, method = "GET", body?: object | string, rows = false) {
  const reply = await fetch(base + path, {
    method, signal: AbortSignal.timeout(6000),
    headers: {apikey: credential, Authorization: `Bearer ${credential}`, "Content-Type": "application/json",
      Prefer: rows ? "return=representation" : "return=minimal"},
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!reply.ok) throw new Error(`Database returned ${reply.status}`);
  if (reply.status === 204) return null;
  return await reply.json();
}

Deno.serve(async (request) => {
  const origin = request.headers.get("origin");
  const headers = new Headers({"Cache-Control": "no-store", "Vary": "Origin", "X-Content-Type-Options": "nosniff"});
  if (origin && origins.has(origin)) headers.set("Access-Control-Allow-Origin", origin);
  const send = (body: object, status = 200) => Response.json(body, {status, headers});
  if (origin && !origins.has(origin)) return send({error: "pair_failed"}, 403);
  if (request.method === "OPTIONS") {
    headers.set("Access-Control-Allow-Methods", "POST");
    headers.set("Access-Control-Allow-Headers", "Content-Type");
    return new Response(null, {status: 204, headers});
  }
  if (request.method !== "POST") return send({error: "invalid_request"}, 405);

  let input;
  try {
    const stream = request.body?.getReader();
    if (!stream) return send({error: "invalid_request"}, 400);
    const decoder = new TextDecoder();
    let size = 0, raw = "";
    for (;;) {
      const {done, value} = await stream.read();
      if (done) break;
      size += value.byteLength;
      if (size > 12288) {
        await stream.cancel();
        return send({error: "invalid_request"}, 413);
      }
      raw += decoder.decode(value, {stream: true});
    }
    input = JSON.parse(raw + decoder.decode());
    if (!input || typeof input !== "object" || Array.isArray(input)) throw new Error();
  } catch {
    return send({error: "invalid_request"}, 400);
  }

  try {
    const {action, code, key, sdp} = input;
    if (action === "offer" || action === "lookup" || action === "answer") {
      const client = request.headers.get("cf-connecting-ip") ??
        request.headers.get("x-forwarded-for")?.split(",").at(-1)?.trim() ?? "unknown";
      const allowed = await database("rpc/xiang_allow_pair_request", "POST", {
        p_source: client,
        p_offer: action === "offer",
      });
      if (!allowed) return send({error: "try_later"}, 429);
    }
    if (action === "offer") {
      if (!validDescription(sdp)) return send({error: "invalid_request"}, 400);
      const secret = crypto.randomUUID();
      for (let attempt = 0; attempt < 3; attempt++) {
        const generated = newCode();
        if (await database("rpc/xiang_create_pair", "POST",
          {p_code: generated, p_host_key: secret, p_offer: sdp})) {
          return send({code: generated, key: secret});
        }
      }
      return send({error: "try_later"}, 429);
    }
    if (typeof code !== "string" || !/^[0-9]{6}$/.test(code)) {
      return send({error: "wrong_code"}, 404);
    }
    const params = new URLSearchParams({code: `eq.${code}`, expires_at: `gt.${new Date().toISOString()}`});
    if (action === "lookup") {
      params.set("select", "offer");
      params.set("answer", "is.null");
      const [room] = await database("xiang_pairs?" + params);
      return room ? send({sdp: room.offer}) : send({error: "wrong_code"}, 404);
    }
    if (typeof key !== "string" || !uuid.test(key)) return send({error: "invalid_request"}, 400);
    if (action === "answer") {
      if (!validDescription(sdp)) return send({error: "invalid_request"}, 400);
      const update = new URLSearchParams(params);
      update.set("answer", "is.null");
      update.set("select", "code");
      const [claimed] = await database("xiang_pairs?" + update, "PATCH", {answer: sdp, guest_key: key}, true);
      if (claimed) return send({});
      params.set("guest_key", `eq.${key}`);
      params.set("select", "code");
      const [retry] = await database("xiang_pairs?" + params);
      return retry ? send({}) : send({error: "room_full"}, 409);
    }
    params.set("host_key", `eq.${key}`);
    if (action === "status") {
      params.set("select", "answer");
      const [room] = await database("xiang_pairs?" + params);
      return room ? send({sdp: room.answer}) : send({error: "room_closed"}, 410);
    }
    if (action === "close") {
      await database("xiang_pairs?" + params, "DELETE");
      return send({});
    }
    return send({error: "invalid_request"}, 400);
  } catch (error) {
    console.error(String(error));
    return send({error: "pair_unavailable"}, 503);
  }
});
