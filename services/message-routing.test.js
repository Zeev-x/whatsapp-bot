import assert from "node:assert/strict";
import test from "node:test";
import {
  extractSenderIdentity,
  extractText,
  getBotJids,
  getBotReplyTarget,
  isBotMentioned,
  isReplyToBot,
  isDeleteCommand,
} from "./message-routing.js";

test("extracts text and mention metadata from group messages", () => {
  const message = {
    extendedTextMessage: {
      text: "Tolong cek suhu komputer",
      contextInfo: {
        mentionedJid: ["628123456789@s.whatsapp.net"],
      },
    },
  };

  assert.deepEqual(extractText(message), {
    text: "Tolong cek suhu komputer",
    contextInfo: {
      mentionedJid: ["628123456789@s.whatsapp.net"],
    },
  });
});

test("recognizes the bot mention even when the JID has a device suffix", () => {
  const message = {
    extendedTextMessage: {
      text: "@Reyette tolong bantu",
      contextInfo: {
        mentionedJid: ["628123456789@s.whatsapp.net"],
      },
    },
  };

  assert.equal(
    isBotMentioned(message, ["628123456789:4@s.whatsapp.net"]),
    true,
  );
});

test("includes phone, LID, and primary IDs when identifying the bot", () => {
  assert.deepEqual(
    getBotJids({
      id: "98765@lid",
      jid: "628123456789@s.whatsapp.net",
      lid: "98765@lid",
    }),
    ["98765@lid", "628123456789@s.whatsapp.net"],
  );

  const message = {
    extendedTextMessage: {
      text: "@Bot tolong bantu",
      contextInfo: {
        mentionedJid: ["628123456789@s.whatsapp.net"],
      },
    },
  };
  assert.equal(
    isBotMentioned(message, getBotJids({
      id: "98765@lid",
      jid: "628123456789@s.whatsapp.net",
    })),
    true,
  );
});

test("does not treat a mention of another member as a bot mention", () => {
  const message = {
    extendedTextMessage: {
      text: "@Teman apa kabar?",
      contextInfo: {
        mentionedJid: ["628987654321@s.whatsapp.net"],
      },
    },
  };

  assert.equal(
    isBotMentioned(message, ["628123456789@s.whatsapp.net"]),
    false,
  );
});

test("recognizes a group reply quoting the bot's JID", () => {
  const message = {
    extendedTextMessage: {
      text: "Bisa jelaskan lebih lanjut?",
      contextInfo: {
        stanzaId: "bot-message-1",
        participant: "628123456789@s.whatsapp.net",
      },
    },
  };

  assert.equal(
    isReplyToBot(
      message,
      "12345@g.us",
      ["628123456789:4@s.whatsapp.net"],
    ),
    true,
  );
});

test("recognizes group reply when bot identity is in participant LID/PN fields", () => {
  const message = {
    extendedTextMessage: {
      text: "Lanjutkan",
      contextInfo: {
        stanzaId: "bot-message-lid",
        participant: "unknown@s.whatsapp.net",
        participantLid: "98765@lid",
      },
    },
  };

  assert.equal(
    isReplyToBot(message, "12345@g.us", ["98765@lid"]),
    true,
  );
});

test("recognizes replies using IDs of bot messages sent in this session", () => {
  const message = {
    extendedTextMessage: {
      text: "Lanjutkan",
      contextInfo: {
        stanzaId: "bot-message-2",
        participant: "unknown@s.whatsapp.net",
      },
    },
  };

  assert.equal(
    isReplyToBot(
      message,
      "12345@g.us",
      ["628123456789@s.whatsapp.net"],
      new Map([
        [
          "12345@g.us:bot-message-2",
          {
            remoteJid: "12345@g.us",
            id: "bot-message-2",
            fromMe: true,
          },
        ],
      ]),
    ),
    true,
  );
});

test("builds a delete key only for a reply to the bot", () => {
  const message = {
    extendedTextMessage: {
      text: "Hapus pesan ini",
      contextInfo: {
        stanzaId: "bot-message-3",
        participant: "628123456789@s.whatsapp.net",
      },
    },
  };

  assert.deepEqual(
    getBotReplyTarget(
      message,
      "12345@g.us",
      ["628123456789:4@s.whatsapp.net"],
    ),
    {
      remoteJid: "12345@g.us",
      id: "bot-message-3",
      fromMe: true,
      participant: "628123456789@s.whatsapp.net",
    },
  );
});

test("does not create delete keys for replies to other participants", () => {
  const message = {
    extendedTextMessage: {
      text: "Hapus pesan ini",
      contextInfo: {
        stanzaId: "member-message-2",
        participant: "628987654321@s.whatsapp.net",
      },
    },
  };

  assert.equal(
    getBotReplyTarget(
      message,
      "12345@g.us",
      ["628123456789@s.whatsapp.net"],
    ),
    null,
  );
});

test("does not treat a reply to another group member as a bot reply", () => {
  const message = {
    extendedTextMessage: {
      text: "Setuju",
      contextInfo: {
        stanzaId: "member-message-1",
        participant: "628987654321@s.whatsapp.net",
      },
    },
  };

  assert.equal(
    isReplyToBot(
      message,
      "12345@g.us",
      ["628123456789@s.whatsapp.net"],
    ),
    false,
  );
});

test("recognizes explicit delete commands but not unrelated sentences", () => {
  for (const command of [
    "hapus",
    "Hapus pesan ini",
    "hapus yang lainnya",
    "tolong hapus yang di-reply",
    "hapus yang tadi dong",
    "delete this message",
  ]) {
    assert.equal(isDeleteCommand(command), true, command);
  }

  for (const text of [
    "jangan hapus pesan ini",
    "hapus aplikasi itu nanti",
    "bisa hapus?",
    "aku hapus pesan ini",
  ]) {
    assert.equal(isDeleteCommand(text), false, text);
  }
});

test("extracts captions and mention metadata from wrapped media", () => {
  const message = {
    ephemeralMessage: {
      message: {
        imageMessage: {
          caption: "Cek status ini",
          contextInfo: {
            mentionedJid: ["628123456789@s.whatsapp.net"],
          },
        },
      },
    },
  };

  assert.equal(extractText(message).text, "Cek status ini");
  assert.equal(
    isBotMentioned(message, ["628123456789@s.whatsapp.net"]),
    true,
  );
});

test("uses WhatsApp profile name and group participant identity", () => {
  const message = {
    key: {
      participant: "628123456789@s.whatsapp.net",
    },
    pushName: "  Rani  ",
  };

  assert.deepEqual(
    extractSenderIdentity(message, "12345@g.us", true),
    {
      senderId: "628123456789@s.whatsapp.net",
      senderName: "Rani",
    },
  );
  assert.deepEqual(
    extractSenderIdentity(message, "628123456789@s.whatsapp.net", false),
    {
      senderId: "628123456789@s.whatsapp.net",
      senderName: "Rani",
    },
  );
});
