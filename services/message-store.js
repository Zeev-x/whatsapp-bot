const MAX_STORED_MESSAGES = 2000;

export function createMessageStore(limit = MAX_STORED_MESSAGES) {
  const messages = new Map();

  return {
    get(key) {
      if (!key?.remoteJid || !key?.id) {
        return undefined;
      }
      return messages.get(`${key.remoteJid}:${key.id}`);
    },

    set(key, message) {
      if (!key?.remoteJid || !key?.id || !message) {
        return;
      }

      const messageKey = `${key.remoteJid}:${key.id}`;
      messages.delete(messageKey);
      messages.set(messageKey, message);

      if (messages.size > limit) {
        messages.delete(messages.keys().next().value);
      }
    },
  };
}
