
from core.ai_engine import AIEngine
from core.safety import SafetyEngine


class MessageProcessor:

    def __init__(self):

        self.ai = AIEngine()
        self.safety = SafetyEngine()

        self.enabled = True

    def process(self, chat_id, message, sender_name=None, memory_chat_id=None):

        if not self.enabled:
            return None

        if not message or not message.strip():
            return None

        answer = self.ai.generate(
            chat_id,
            message.strip(),
            sender_name=sender_name,
            memory_chat_id=memory_chat_id,
        )

        if not self.safety.validate(message, answer):
            return None

        return {
            "type": "ai",
            "response": answer
        }

    def set_enabled(self, enabled):
        self.enabled = enabled

    def clear_memory(self):
        self.ai.clear_all()
