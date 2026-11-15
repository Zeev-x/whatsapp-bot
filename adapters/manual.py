from adapters.base import ReplyAdapter


class ManualAdapter(ReplyAdapter):

    def send(self, chat_id, message):

        # Tidak mengirim pesan ke WhatsApp.
        # Hanya menyiapkan hasil AI untuk ditinjau.
        return {
            "chat_id": chat_id,
            "message": message,
            "status": "pending_manual_review"
        }