import makeWASocket, {
  Browsers,
  DisconnectReason,
  useMultiFileAuthState,
} from "@whiskeysockets/baileys";
import pino from "pino";
import QRCode from "qrcode";
import { createInterface } from "node:readline";
import { mkdir } from "node:fs/promises";
import {
  extractSenderIdentity,
  extractText,
  getBotJids,
  getBotReplyTarget,
  isBotMentioned,
  isReplyToBot,
  isDeleteCommand,
} from "./message-routing.js";
import { createMessageStore } from "./message-store.js";

const authDirectory = process.argv[2];
if (!authDirectory) {
  throw new Error("Missing WhatsApp auth directory argument.");
}

await mkdir(authDirectory, { recursive: true });

let socket;
let reconnectTimer;
let stopping = false;
let connected = false;
const seenMessageIds = new Set();
const botMessageKeys = new Map();
const messageStore = createMessageStore();

function emit(event) {
  process.stdout.write(`${JSON.stringify(event)}\n`);
}

async function connect() {
  const { state, saveCreds } = await useMultiFileAuthState(authDirectory);
  socket = makeWASocket({
    auth: state,
    browser: Browsers.windows("Reyette WhatsApp"),
    logger: pino({ level: "silent" }),
    getMessage: async (key) => messageStore.get(key),
  });

  socket.ev.on("creds.update", saveCreds);

  socket.ev.on("connection.update", async (update) => {
    if (update.qr) {
      try {
        emit({
          type: "qr",
          image: await QRCode.toDataURL(update.qr, {
            margin: 2,
            width: 360,
          }),
        });
      } catch (error) {
        emit({ type: "error", message: `Gagal membuat QR: ${error.message}` });
      }
    }

    if (update.connection === "open") {
      connected = true;
      emit({ type: "connected" });
    } else if (update.connection === "close") {
      connected = false;
      const statusCode = update.lastDisconnect?.error?.output?.statusCode;
      const loggedOut = statusCode === DisconnectReason.loggedOut;

      emit({
        type: "disconnected",
        message: loggedOut
          ? "Sesi WhatsApp berakhir. Hapus data/whatsapp_auth lalu jalankan ulang untuk memindai QR baru."
          : "Koneksi terputus; mencoba menyambung ulang.",
      });

      if (!loggedOut && !stopping) {
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(() => {
          connect().catch((error) =>
            emit({ type: "error", message: `Gagal menyambung: ${error.message}` }),
          );
        }, 1500);
      }
    }
  });

  socket.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") {
      return;
    }

    for (const message of messages) {
      const chatId = message.key?.remoteJid;
      const messageId = message.key?.id;
      const { text } = extractText(message.message);
      const isGroup = chatId?.endsWith("@g.us");
      const { senderId, senderName } = extractSenderIdentity(
        message,
        chatId,
        isGroup,
      );
      const botJids = getBotJids(socket.user);
      const isBotMention = isBotMentioned(message.message, botJids);
      const isBotReply = isReplyToBot(
        message.message,
        chatId,
        botJids,
        botMessageKeys,
      );

      if (
        message.key?.fromMe ||
        !chatId ||
        chatId === "status@broadcast" ||
        !text ||
        (isGroup && !isBotMention && !isBotReply) ||
        (messageId && seenMessageIds.has(messageId))
      ) {
        continue;
      }

      if (isDeleteCommand(text)) {
        const target = getBotReplyTarget(
          message.message,
          chatId,
          botJids,
          botMessageKeys,
        );
        if (target) {
          try {
            await socket.sendMessage(chatId, { delete: target });
            botMessageKeys.delete(`${chatId}:${target.id}`);
            emit({
              type: "deleted",
              chat_id: chatId,
              message_id: target.id,
            });
          } catch (error) {
            emit({
              type: "error",
              message: `Gagal menghapus pesan bot: ${error.message}`,
            });
          }
          continue;
        }
      }

      if (messageId) {
        seenMessageIds.add(messageId);
        if (seenMessageIds.size > 500) {
          seenMessageIds.delete(seenMessageIds.values().next().value);
        }
      }

      emit({
        type: "message",
        chat_id: chatId,
        sender_id: senderId,
        sender_name: senderName,
        text,
        is_group: isGroup,
      });
    }
  });
}

const input = createInterface({ input: process.stdin });
input.on("line", async (line) => {
  let command;
  try {
    command = JSON.parse(line);
  } catch (error) {
    emit({ type: "error", message: `Perintah tidak valid: ${error.message}` });
    return;
  }

  if (command.type === "send") {
    if (!connected || !socket) {
      emit({ type: "error", message: "WhatsApp belum terhubung; balasan tidak dikirim." });
      return;
    }
    if (
      typeof command.chat_id !== "string" ||
      typeof command.text !== "string" ||
      !command.text.trim()
    ) {
      emit({ type: "error", message: "Tujuan atau isi balasan tidak valid." });
      return;
    }

    try {
      const sentMessage = await socket.sendMessage(
        command.chat_id,
        { text: command.text },
      );
      if (sentMessage?.key?.id && sentMessage.message) {
        messageStore.set(sentMessage.key, sentMessage.message);
        const sentKey = {
          remoteJid: command.chat_id,
          id: sentMessage.key.id,
          fromMe: true,
          ...(sentMessage.key.participant
            ? { participant: sentMessage.key.participant }
            : {}),
        };
        botMessageKeys.set(
          `${command.chat_id}:${sentMessage.key.id}`,
          sentKey,
        );
        if (botMessageKeys.size > 1000) {
          botMessageKeys.delete(botMessageKeys.keys().next().value);
        }
      }
      emit({ type: "sent", chat_id: command.chat_id });
    } catch (error) {
      emit({ type: "error", message: `Gagal mengirim balasan: ${error.message}` });
    }
  } else if (command.type === "close") {
    stopping = true;
    clearTimeout(reconnectTimer);
    input.close();
    socket?.end();
    setTimeout(() => process.exit(0), 1000).unref();
  }
});

connect().catch((error) => {
  emit({ type: "error", message: `Gagal memulai WhatsApp: ${error.message}` });
  process.exitCode = 1;
  input.close();
});
