/** Extracted from dsh-wechat-media 1.24.13 (MIT); QX narrows delivery and correlates exact messages. */
const MAX_TEXT_CHARS=2000; const REPLY_TIMEOUT_MS=300000; const DELIVERY_TOOLS=new Set(["wechat_send_file"]);
const FENCE = String.fromCharCode(96, 96, 96);

export function chunkText(text, limit = MAX_TEXT_CHARS) {
  const source = String(text ?? "").trim();
  if (source.length <= limit) return source ? [source] : [];
  const chunks = [];
  let rest = source;
  let insideFence = false;
  while (rest.length > limit) {
    const window = rest.slice(0, limit);
    const cut = Math.max(window.lastIndexOf("\n\n"), window.lastIndexOf("\n"), window.lastIndexOf("。"));
    let at = cut > limit * 0.5 ? cut + 1 : limit;
    // never split a surrogate pair: half of an emoji is an invalid character on the wire, and platforms reject those
    if (at > 0 && at < rest.length) {
      const previous = rest.charCodeAt(at - 1);
      if (previous >= 0xd800 && previous <= 0xdbff) at -= 1;
    }
    if (at <= 0) at = Math.min(limit, rest.length);
    let piece = rest.slice(0, at).trim();
    rest = rest.slice(at).trim();
    // a cut inside a fence closes it here and reopens it in the next chunk, so no chunk shows half a code block
    const fences = (piece.match(/```/g) ?? []).length;
    const nowInside = insideFence !== (fences % 2 === 1);
    if (nowInside && rest) {
      // FENCE is the three-backtick marker; written once so no template literal has to contain it.
      piece = `${piece}\n${FENCE}`;
      rest = `${FENCE}\n${rest}`;
      insideFence = false;
    } else {
      insideFence = nowInside;
    }
    if (piece) chunks.push(piece);
  }
  if (rest) chunks.push(rest);
  return chunks.filter(Boolean);
}
export function liveTextOf(frame) {
  const type = String((frame && typeof frame === "object" && frame.type) || "");
  if (!type || /reason/i.test(type)) return "";
  const text = frame.text;
  if (type === "text-delta") return typeof text === "string" ? text : "";
  if (type === "chunk") {
    const chunk = frame.chunk;
    if (chunk && String(chunk.type) === "text-delta" && typeof chunk.text === "string") return chunk.text;
    return "";
  }
  if (type === "text-chunks" && Array.isArray(frame.texts)) {
    return frame.texts.filter((part) => typeof part === "string").join("");
  }
  return "";
}
export function assistantText(event) {
  const content = event?.data?.message?.content;
  if (!Array.isArray(content)) return "";
  return content
    .filter((block) => block?.type === "text" && typeof block.text === "string")
    .map((block) => block.text)
    .join("");
}
export class ReplyCollector {
  constructor(scope, { onUsage, onDelta, onSettled } = {}) {
    this.scope = scope;
    this.onUsage = onUsage;
    this.onDelta = onDelta;
    this.onSettled = onSettled;
    // Event types this collector does not handle. A bounded ring, reported by /state: if live text
    // arrives under a name nobody told us about, it shows up here instead of vanishing.
    this.unknownEvents = [];
    /**
     * One queue of waiters per session, not one waiter.
     *
     * A second message arriving while the first is still being answered used to *replace* the
     * pending record, so the first reply could never be relayed and the replacement was
     * resolved by the wrong turn. Interjection makes that path normal (the second message is
     * steered into the running turn) and queueing keeps it correct (the second message waits
     * for its own turn).
     */
    this.pending = new Map(); // sessionId -> record[]
    scope.on("agent/inbox/claimed", ({ agent, message, turn }) => {
      const sessionId = String(agent?.session?.id ?? agent?.id ?? "");
      const queue = this.pending.get(sessionId);
      if (!queue?.length) return;
      // Desktop and WeChat share a session: an unrelated desktop claim must never consume a WeChat waiter.
      const record = queue.find((candidate) => candidate.turn === undefined && candidate.messageId && candidate.messageId === message?.id)
        ?? queue.find((candidate) => candidate.turn === undefined && !candidate.messageId);
      if (record) record.turn = turn;
    });
    scope.on("agent/assistant-stream", ({ frame } = {}) => {
      // Every frame is reported, in whatever shape it arrives, and with whatever text it carries
      // (possibly none). Deciding "is this text worth showing" here would hide the difference
      // between "no frames arrive" and "frames arrive in a shape we do not know".
      try {
        this.onDelta?.({ text: liveTextOf(frame), type: String(frame?.type ?? "?") });
      } catch {
        /* never let a preview take the answer down */
      }
    });
    scope.on("session/event", (session, event) => {
      const sessionId = String(session?.header?.id ?? session?.id ?? "");
      // Token usage is reported per model call, not per turn, and it is interesting even for
      // a session no chat is waiting on (a GUI turn of the same conversation, say), so it is
      // accounted before the `pending` bookkeeping and independently of it.
      if (event.type === "assistant/message" && event.data?.usage) {
        try {
          this.onUsage?.({ sessionId, usage: event.data.usage, step: event.data?.step });
        } catch {
          // Counting must never be the reason a reply is lost.
        }
      }
      // Live text may also travel as a session event (non-durable, so it never reaches the
      // transcript). Accept a delta-shaped one, never a reasoning one, and record what came.
      if (/delta/i.test(String(event.type)) && !/reason|think/i.test(String(event.type))) {
        const chunk = event.data?.text ?? event.data?.delta ?? event.data?.content;
        if (typeof chunk === "string" && chunk) {
          this.unknownEvents.push(`${event.type}:text`);
          if (this.unknownEvents.length > 12) this.unknownEvents.shift();
          try {
            this.onDelta?.({ text: chunk, type: `${event.type} (session)` });
          } catch {
            /* a preview must never break the reply */
          }
        }
      } else if (!["tool/call", "assistant/message", "turn/end", "turn/start", "step/start", "step/end", "user/message", "request/header"].includes(String(event.type))) {
        this.unknownEvents.push(String(event.type));
        if (this.unknownEvents.length > 12) this.unknownEvents.shift();
      }
      const queue = this.pending.get(sessionId);
      if (!queue?.length) return;
      // The text of a turn belongs to the record that turn was claimed for.
      const forTurn = queue.filter((record) => record.turn !== undefined && record.turn === event?.data?.turn);
      if (event.type === "tool/call") {
        // A delivery tool already answered this turn: remember it so the relay
        // does not send the same answer a second time.
        if (DELIVERY_TOOLS.has(String(event.data?.name ?? ""))) for (const record of forTurn) record.deliveredByTool = true;
        return;
      }
      if (event.type === "assistant/message") {
        const text = assistantText(event);
        if (text) for (const record of forTurn) record.parts.push(text);
        return;
      }
      if (event.type === "turn/end") {
        for (const record of forTurn) {
          this.#settle(record, { text: record.parts.join("").trim(), stopReason: event.data?.reason?.kind ?? "end_turn" });
        }
      }
    });
    scope.on("agent/error", ({ agent, turn, error }) => {
      const sessionId = String(agent?.session?.id ?? agent?.id ?? "");
      const queue = this.pending.get(sessionId);
      if (!queue?.length) return;
      for (const record of queue.filter((candidate) => candidate.turn !== undefined && candidate.turn === turn)) {
        this.#settle(record, { text: record.parts.join("").trim(), error: String(error?.message ?? error), stopReason: "error" });
      }
    });
  }

  /** Is a reply for this session still being awaited? (`/interject` asks exactly this.) */
  isWaiting(sessionId) {
    return (this.pending.get(String(sessionId)) ?? []).length > 0;
  }

  #settle(record, outcome) {
    if (record.settled) return;
    record.settled = true;
    clearTimeout(record.timer);
    clearTimeout(record.claimTimer);
    const queue = this.pending.get(record.sessionId) ?? [];
    const remaining = queue.filter((candidate) => candidate !== record);
    if (remaining.length > 0) this.pending.set(record.sessionId, remaining);
    else this.pending.delete(record.sessionId);
    // Everyone who wants to know that a turn finished hears it here, once: a webhook that were emitted by each transport
    // separately would be emitted three times for the same turn, and a fourth would be missing.
    try {
      this.onSettled?.({ sessionId: record.sessionId, ...outcome });
    } catch {
      /* an observer must never cost the reply */
    }
    record.resolve({ ...outcome, deliveredByTool: Boolean(record.deliveredByTool) });
  }

  /**
   * Wait for the reply to one message.
   * @param {string} sessionId
   * @param {string|undefined} messageId id of the message we queued, when known
   * @returns {Promise<{ text: string, stopReason: string, error?: string }>}
   */
  wait(sessionId, messageId, timeoutMs = REPLY_TIMEOUT_MS) {
    return new Promise((resolve) => {
      const record = {
        sessionId,
        messageId,
        turn: undefined,
        parts: [],
        settled: false,
        resolve,
        timer: setTimeout(() => this.#settle(record, { text: record.parts.join("").trim(), stopReason: "timeout" }), timeoutMs),
      };
      const queue = this.pending.get(sessionId) ?? [];
      queue.push(record);
      this.pending.set(sessionId, queue);
      // If the inbox never claims it (admission gate), do not wait forever.
      record.claimTimer = setTimeout(() => {
        if (!record.settled && record.turn === undefined) {
          this.#settle(record, { text: record.parts.join("").trim(), stopReason: "not-claimed" });
        }
      }, 15_000);
    });
  }
}
