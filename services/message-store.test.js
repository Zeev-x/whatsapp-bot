import assert from "node:assert/strict";
import test from "node:test";
import { createMessageStore } from "./message-store.js";

test("returns the stored message by chat and message ID for retries", () => {
  const store = createMessageStore();
  const message = { conversation: "Balasan bot" };

  store.set(
    { remoteJid: "12345@g.us", id: "message-1" },
    message,
  );

  assert.equal(
    store.get({ remoteJid: "12345@g.us", id: "message-1" }),
    message,
  );
  assert.equal(
    store.get({ remoteJid: "another@g.us", id: "message-1" }),
    undefined,
  );
});

test("evicts the oldest messages when the configured limit is reached", () => {
  const store = createMessageStore(2);
  store.set({ remoteJid: "chat", id: "one" }, { conversation: "one" });
  store.set({ remoteJid: "chat", id: "two" }, { conversation: "two" });
  store.set({ remoteJid: "chat", id: "three" }, { conversation: "three" });

  assert.equal(store.get({ remoteJid: "chat", id: "one" }), undefined);
  assert.deepEqual(
    store.get({ remoteJid: "chat", id: "two" }),
    { conversation: "two" },
  );
  assert.deepEqual(
    store.get({ remoteJid: "chat", id: "three" }),
    { conversation: "three" },
  );
});

test("ignores incomplete keys and empty message bodies", () => {
  const store = createMessageStore();

  store.set({ remoteJid: "chat" }, { conversation: "message" });
  store.set({ remoteJid: "chat", id: "empty" }, undefined);

  assert.equal(store.get({ remoteJid: "chat" }), undefined);
  assert.equal(store.get({ remoteJid: "chat", id: "empty" }), undefined);
});
