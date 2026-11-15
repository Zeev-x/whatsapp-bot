import { areJidsSameUser } from "@whiskeysockets/baileys";

const MESSAGE_WRAPPERS = [
  "ephemeralMessage",
  "viewOnceMessage",
  "viewOnceMessageV2",
  "documentWithCaptionMessage",
];

const TEXT_MESSAGE_TYPES = [
  "extendedTextMessage",
  "imageMessage",
  "videoMessage",
  "documentMessage",
];

function unwrapMessage(message) {
  let content = message;
  for (let depth = 0; depth < MESSAGE_WRAPPERS.length; depth += 1) {
    const wrapper = MESSAGE_WRAPPERS.find((key) => content?.[key]?.message);
    if (!wrapper) {
      break;
    }
    content = content[wrapper].message;
  }
  return content;
}

export function extractText(message) {
  const content = unwrapMessage(message);
  const text =
    content?.conversation ??
    TEXT_MESSAGE_TYPES.map((type) => content?.[type]?.text ?? content?.[type]?.caption)
      .find(Boolean) ??
    "";

  return {
    text: text.trim(),
    contextInfo:
      TEXT_MESSAGE_TYPES.map((type) => content?.[type]?.contextInfo)
        .find(Boolean) ??
      content?.contextInfo,
  };
}

export function getBotJids(user) {
  if (!user || typeof user !== "object") {
    return [];
  }

  return [...new Set([user.id, user.jid, user.lid].filter(
    (jid) => typeof jid === "string" && jid.length > 0,
  ))];
}

export function isBotMentioned(message, botJids) {
  const { contextInfo } = extractText(message);
  const mentionedJids = contextInfo?.mentionedJid;
  if (!Array.isArray(mentionedJids) || !Array.isArray(botJids)) {
    return false;
  }

  return mentionedJids.some(
    (mentionedJid) =>
      typeof mentionedJid === "string" &&
      botJids.some(
        (botJid) =>
          typeof botJid === "string" &&
          areJidsSameUser(mentionedJid, botJid),
      ),
  );
}

export function isReplyToBot(message, chatId, botJids, botMessageKeys = new Map()) {
  return getBotReplyTarget(message, chatId, botJids, botMessageKeys) !== null;
}

export function getBotReplyTarget(
  message,
  chatId,
  botJids,
  botMessageKeys = new Map(),
) {
  const { contextInfo } = extractText(message);
  const stanzaId = contextInfo?.stanzaId;
  if (
    typeof chatId !== "string" ||
    typeof stanzaId !== "string" ||
    !stanzaId
  ) {
    return null;
  }

  const participants = [
    contextInfo.participant,
    contextInfo.participantPn,
    contextInfo.participantLid,
  ].filter((jid) => typeof jid === "string");
  const participant = participants.find(
    (jid) =>
      Array.isArray(botJids) &&
      botJids.some(
        (botJid) =>
          typeof botJid === "string" &&
          areJidsSameUser(jid, botJid),
      ),
  );
  const authorIsBot = Boolean(participant);
  const trackedKey = botMessageKeys.get(`${chatId}:${stanzaId}`);

  if (!authorIsBot && !trackedKey) {
    return null;
  }

  return {
    remoteJid: chatId,
    id: stanzaId,
    fromMe: true,
    ...((authorIsBot ? participant : trackedKey?.participant)
      ? {
          participant: authorIsBot
            ? participant
            : trackedKey.participant,
        }
      : {}),
  };
}

export function isDeleteCommand(text) {
  return /^(?:tolong\s+)?(?:hapus|delete|remove)(?:\s+(?:(?:pesan|message)(?:\s+(?:ini|itu|this|that|tersebut|tadi|lainnya|yang\s+(?:ini|itu|tadi|lainnya|di-?reply|saya\s+reply|aku\s+reply)))?|(?:yang|yg)\s+(?:ini|itu|tadi|lainnya|tersebut|di-?reply|saya\s+reply|aku\s+reply)|ini|itu|this|that|tersebut|tadi|lainnya|dong|ya|please))*[.!?]*$/i.test(
    text.trim(),
  );
}

export function extractSenderIdentity(message, chatId, isGroup) {
  return {
    senderId: isGroup ? message.key?.participant : chatId,
    senderName:
      typeof message.pushName === "string" ? message.pushName.trim() : "",
  };
}
