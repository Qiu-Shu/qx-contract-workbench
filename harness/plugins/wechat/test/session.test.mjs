/**
 * Tests for durable session identity: only a classified absence permits creation.
 * Ambiguous restore failures and occupied identities must never discard history
 * by replacing the requested conversation with an empty one.
 *
 * Run: node test/session.test.mjs
 */
import assert from "node:assert/strict";

import { describeError, isSessionExistsError, openSessionAgent } from "../session.js";
import { sessionIdFor } from "../index.js";

let passed = 0;
let failed = 0;
async function test(name, fn) {
  try {
    await fn();
    passed += 1;
    console.log(`  ok   ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`  FAIL ${name}\n       ${error?.message ?? error}`);
  }
}

/** An `ctx.agents` double: scripted answers per call, recording every request. */
function stubAgents(script) {
  const calls = { resume: [], create: [] };
  const handleFor = (id) => ({ id, dispose: async () => {} });
  return {
    calls,
    async resume(options) {
      calls.resume.push(options);
      const step = script.resume.shift();
      if (step instanceof Error) throw step;
      return handleFor(step?.id ?? options.resumeSessionId);
    },
    async create(options) {
      calls.create.push(options);
      const step = script.create.shift();
      if (step instanceof Error) throw step;
      return handleFor(step?.id ?? options.sessionId);
    },
  };
}

const alreadyExists = (id) => Object.assign(new Error(`session "${id}" already exists`), { name: "SessionAlreadyExistsError" });

console.log("session ladder");

console.log("-- error classification --");

await test("the persistence errors are recognised by name or by wording", () => {
  assert.equal(isSessionExistsError(alreadyExists("wechat-1")), true);
  assert.equal(isSessionExistsError(Object.assign(new Error("session x is already owned"), { name: "SessionAlreadyOwnedError" })), true);
  assert.equal(isSessionExistsError(new Error("session persistence is not configured")), false);
  assert.equal(isSessionExistsError(undefined), false);
});

await test("a described error is one readable line", () => {
  assert.equal(describeError(new Error("boom")), "boom");
  assert.equal(describeError({ name: "WeirdError" }), "WeirdError");
  assert.equal(describeError("plain"), "plain");
});

console.log("-- the ordinary paths --");

await test("a resumable session is resumed and reported as clean", async () => {
  const agents = stubAgents({ resume: [{}], create: [] });
  const { handle, issue } = await openSessionAgent({ agents, sessionId: "wechat-a", meta: { cwd: "/inbox" } });
  assert.equal(handle.id, "wechat-a");
  assert.equal(issue, undefined);
  assert.equal(agents.calls.resume.length, 1);
  assert.equal(agents.calls.create.length, 0);
});

await test("a classified absent session creates exactly the requested identity", async () => {
  class Missing extends Error {}
  const agents = stubAgents({ resume: [new Missing('session "wechat-a" not found')], create: [{}] });
  const { handle, sessionId } = await openSessionAgent({ agents, sessionId: "wechat-a", isMissingSession: error => error instanceof Missing });
  assert.equal(handle.id, "wechat-a");
  assert.equal(sessionId, "wechat-a");
  assert.deepEqual(agents.calls.create.map(options => options.sessionId), ["wechat-a"]);
});

await test("meta, agentOptions and setup reach whichever call succeeds", async () => {
  const setup = async () => {};
  const missing = new Error("classified absent");
  const agents = stubAgents({ resume: [missing], create: [{}] });
  await openSessionAgent({
    agents,
    sessionId: "wechat-b",
    meta: { cwd: "/inbox", agentPreset: "default" },
    agentOptions: { provider: "deepseek-official", model: "deepseek-flash" },
    setup,
    isMissingSession: error => error === missing,
  });
  const [options] = agents.calls.create;
  assert.deepEqual(options.meta, { cwd: "/inbox", agentPreset: "default" });
  assert.equal(options.agentOptions.model, "deepseek-flash");
  assert.equal(options.setup, setup);
  assert.deepEqual(agents.calls.resume[0].meta, options.meta);
  assert.equal(agents.calls.resume[0].agentOptions.model, "deepseek-flash");
  assert.equal(agents.calls.resume[0].setup, setup);
});

console.log("-- recovery: the live wedge --");

await test("a creation conflict is surfaced without a replacement id or implicit retry", async () => {
  const missing = new Error('session "wechat-c" not found');
  const agents = stubAgents({ resume: [missing, {}], create: [alreadyExists("wechat-c")] });
  await assert.rejects(() => openSessionAgent({ agents, sessionId: "wechat-c", isMissingSession: error => error === missing }), /already exists/);
  assert.deepEqual(agents.calls.create.map(options => options.sessionId), ["wechat-c"]);
  assert.equal(agents.calls.resume.length, 1);
});

await test("an unclassified not-found message cannot authorize a fresh empty session", async () => {
  const agents = stubAgents({
    resume: [new Error("not found"), alreadyExists("wechat-d")],
    create: [alreadyExists("wechat-d"), {}],
  });
  await assert.rejects(() => openSessionAgent({ agents, sessionId: "wechat-d" }), /not found.*已保留原会话/);
  assert.equal(agents.calls.create.length, 0);
  assert.equal(agents.calls.resume.length, 1);
});

await test("an ambiguous restore keeps the original error and never reaches creation", async () => {
  const original = new Error("corrupt persistence log");
  const agents = stubAgents({
    resume: [original, alreadyExists("wechat-e")],
    create: [alreadyExists("wechat-e"), new Error("no persistence backend")],
  });
  await assert.rejects(
    () => openSessionAgent({ agents, sessionId: "wechat-e" }),
    (error) => {
      assert.match(error.message, /wechat-e.*corrupt persistence log.*已保留原会话/);
      assert.equal(error.cause, original);
      return true;
    },
  );
  assert.equal(agents.calls.create.length, 0);
});

await test("a create failure that is not an id clash is reported, not papered over", async () => {
  const missing = new Error("classified absent");
  const agents = stubAgents({ resume: [missing], create: [new Error("provider is not configured")] });
  await assert.rejects(
    () => openSessionAgent({ agents, sessionId: "wechat-f", isMissingSession: error => error === missing }),
    (error) => {
      assert.match(error.message, /provider is not configured/);
      return true;
    },
  );
  assert.equal(agents.calls.create.length, 1, "no pointless fresh-id attempt after a real failure");
  assert.equal(agents.calls.resume.length, 1);
  assert.equal(agents.calls.create[0].sessionId, "wechat-f");
});

await test("a missing agents service is refused with a readable message", async () => {
  await assert.rejects(() => openSessionAgent({ sessionId: "wechat-g" }), /session identity and agents service required/);
  await assert.rejects(() => openSessionAgent({ agents: { resume: async () => {} }, sessionId: "x" }), /session identity and agents service required/);
  await assert.rejects(
    () => openSessionAgent({ agents: { resume: async () => {}, create: async () => {} }, sessionId: "" }),
    /session identity and agents service required/,
  );
});

console.log("-- one conversation per chat --");

// A stand-in with the real shape: `wecom:` + a 35-character BotID, so the account id
// alone is longer than the 30 bytes the old id rule had room for. Deliberately fake.
const WECOM_ACCOUNT = "wecom-example0BotId0NotReal0000000000000";

await test("every chat of one account gets its own session id", () => {
  // The historical bug: the id was the first 40 base64url characters of
  // `${accountId}\0${chatId}` (~30 bytes) while a WeCom account id alone is 41
  // characters, so all four of these resolved to ONE id - a direct message, a group
  // and a debug chat sharing a conversation. Verified live before the fix.
  const chats = [
    "woIHRNCwEXAMPLEchatId00000000000",
    "debug-verify-1",
    "another-chat-2",
    "12345678@chatroom",
  ];
  const ids = chats.map((chat) => sessionIdFor(WECOM_ACCOUNT, chat));
  assert.equal(new Set(ids).size, chats.length, `expected one id per chat, got ${JSON.stringify(ids)}`);
});

await test("the same chat under different accounts is a different conversation", () => {
  const chat = "woIHRNCwEXAMPLEchatId00000000000";
  assert.notEqual(sessionIdFor("b775a478733a-im-bot", chat), sessionIdFor(WECOM_ACCOUNT, chat));
});

await test("two personal chats that share a long prefix do not merge either", () => {
  const account = "b775a478733a-im-bot";
  const a = "o9cq804M3lHB9fiVfj9vwwBe_hpc@im.wechat";
  const b = "o9cq804M3lHB9fiVfj9vwwBe_other@im.wechat";
  assert.notEqual(sessionIdFor(account, a), sessionIdFor(account, b));
});

await test("the id is stable, short and filesystem-safe", () => {
  const first = sessionIdFor(WECOM_ACCOUNT, "chat-1");
  assert.equal(first, sessionIdFor(WECOM_ACCOUNT, "chat-1"), "a restart must resolve to the same conversation");
  assert.match(first, /^wechat-[A-Za-z0-9]{32}$/);
  assert.ok(first.length <= 40, "session ids become directory names");
});

console.log("-- /new restarts a conversation --");

await test("generation 0 is exactly what earlier releases computed", () => {
  // Backwards compatibility: conversations that exist today must keep resolving to them.
  for (const chat of [WECOM_ACCOUNT, "12345678@chatroom", "o9cq804M3lHB9fiVfj9vwwBe_hpc@im.wechat"]) {
    assert.equal(sessionIdFor(WECOM_ACCOUNT, chat), sessionIdFor(WECOM_ACCOUNT, chat, 0));
  }
});

await test("a new generation is a new conversation, and stable within itself", () => {
  const chat = "woIHRNCwEXAMPLEchatId00000000000";
  const ids = [0, 1, 2].map((generation) => sessionIdFor(WECOM_ACCOUNT, chat, generation));
  assert.equal(new Set(ids).size, 3, "every /new must land on its own session id");
  for (const generation of [0, 1, 2]) {
    assert.equal(sessionIdFor(WECOM_ACCOUNT, chat, generation), ids[generation], "the id must not drift between messages");
    assert.match(ids[generation], /^wechat-[A-Za-z0-9]{32}$/);
  }
});

await test("generations do not collide across chats, and junk input falls back to 0", () => {
  const account = "b775a478733a-im-bot";
  assert.notEqual(sessionIdFor(account, "chat-a", 1), sessionIdFor(account, "chat-b", 1));
  assert.equal(sessionIdFor(account, "chat-a", "nonsense"), sessionIdFor(account, "chat-a", 0));
  assert.equal(sessionIdFor(account, "chat-a", -3), sessionIdFor(account, "chat-a", 0));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
