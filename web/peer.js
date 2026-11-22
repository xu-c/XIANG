"use strict";

const SIGNAL_URL = "/api/pair";
const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

async function signalRoom(action, data) {
  const response = await fetch(SIGNAL_URL, {method: "POST", credentials: "omit", redirect: "error",
    headers: {"Content-Type": "application/json"}, body: JSON.stringify({action, ...data}),
    signal: AbortSignal.timeout(10000)});
  const reply = await response.json();
  if (!response.ok) throw new Error(reply.error || "pair_unavailable");
  return reply;
}

function gatherIce(pc) {
  return new Promise(resolve => {
    const done = () => {
      clearTimeout(timer);
      pc.removeEventListener("icegatheringstatechange", check);
      resolve();
    };
    const check = () => { if (pc.iceGatheringState === "complete") done(); };
    const timer = setTimeout(done, 4000);
    pc.addEventListener("icegatheringstatechange", check);
    check();
  });
}

class BrowserPeer {
  constructor(match = null) {
    // Host ICE candidates only. The signaling endpoint does not relay moves.
    this.pc = new RTCPeerConnection({iceServers: []});
    this.match = match;
    this.pending = new Map();
    this.sequence = 0;
    this.closed = false;
    this.error = "";
    this.receipt = null;
    this.pc.addEventListener("connectionstatechange", () => {
      if (this.pc.connectionState === "failed" && !this.closed) this.close("pair_failed");
    });
  }

  attach(channel) {
    if (channel.label !== "xiang") {
      channel.close();
      return;
    }
    this.channel = channel;
    channel.onopen = () => { if (this.match) this.match.ready = true; };
    channel.onclose = () => { if (!this.closed) this.close("room_closed"); };
    channel.onmessage = event => {
      if (typeof event.data !== "string" || event.data.length > 65536) return;
      let data;
      try { data = JSON.parse(event.data); } catch { return; }
      if (!data || typeof data !== "object") return;
      if (data.closed && !this.match) {
        this.close("room_closed");
      } else if (this.match && Number.isSafeInteger(data.id)) {
        const reply = {id: data.id};
        try { reply.result = this.match.call(data.action, data.body || {}, 3 - this.match.hostColor); }
        catch (error) { reply.error = error.message; }
        channel.send(JSON.stringify(reply));
      } else if (!this.match && this.pending.has(data.id)) {
        const request = this.pending.get(data.id);
        this.pending.delete(data.id);
        clearTimeout(request.timer);
        if (data.error) request.reject(new Error(data.error));
        else request.resolve(data.result);
      }
    };
  }

  async host() {
    this.attach(this.pc.createDataChannel("xiang"));
    await this.pc.setLocalDescription(await this.pc.createOffer());
    await gatherIce(this.pc);
    this.receipt = await signalRoom("offer", {sdp: this.pc.localDescription.sdp});
    this.waitForAnswer().catch(() => this.close("pair_failed"));
    return {code: this.receipt.code, color: this.match.hostColor, state: this.match.state()};
  }

  async waitForAnswer() {
    const started = Date.now();
    while (!this.closed) {
      let sdp;
      try {
        ({sdp} = await signalRoom("status", this.receipt));
      } catch (error) {
        if (this.closed) return;
        if (error.message === "room_closed") {
          this.close("pair_expired");
          return;
        }
        if (Date.now() - started >= 300000) {
          this.close("pair_expired");
          return;
        }
      }
      if (this.closed) return;
      if (sdp) {
        await this.pc.setRemoteDescription({type: "answer", sdp});
        await this.waitForChannel();
        this.clearReceipt();
        return;
      }
      await delay(Date.now() - started < 30000 ? 1500 : 3500);
    }
  }

  async join(code) {
    this.pc.ondatachannel = event => this.attach(event.channel);
    const {sdp} = await signalRoom("lookup", {code});
    await this.pc.setRemoteDescription({type: "offer", sdp});
    await this.pc.setLocalDescription(await this.pc.createAnswer());
    await gatherIce(this.pc);
    await signalRoom("answer", {code, key: crypto.randomUUID(), sdp: this.pc.localDescription.sdp});
    await this.waitForChannel();
    return this.call("join", {rematch: true});
  }

  async waitForChannel() {
    const deadline = Date.now() + 15000;
    while (!this.closed && Date.now() < deadline) {
      if (this.channel?.readyState === "open") return;
      await delay(100);
    }
    throw new Error("pair_failed");
  }

  async call(action, body) {
    if (this.closed) throw new Error(this.error || "room_closed");
    if (this.match) return this.match.call(action, body, this.match.hostColor);
    if (this.channel?.readyState !== "open") throw new Error("pair_unavailable");
    return await new Promise((resolve, reject) => {
      const id = ++this.sequence;
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error("pair_unavailable"));
      }, 2500);
      this.pending.set(id, {resolve, reject, timer});
      this.channel.send(JSON.stringify({id, action, body}));
    });
  }

  clearReceipt() {
    if (this.receipt) signalRoom("close", this.receipt).catch(() => {});
    this.receipt = null;
  }

  close(error = "") {
    if (this.closed) return;
    this.closed = true;
    this.error = error;
    this.clearReceipt();
    if (this.match && this.channel?.readyState === "open") this.channel.send(JSON.stringify({closed: true}));
    this.pc.close();
    for (const request of this.pending.values()) {
      clearTimeout(request.timer);
      request.reject(new Error(error || "room_closed"));
    }
    this.pending.clear();
  }
}
