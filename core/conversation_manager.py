
class ConversationManager:

    def __init__(self, max_history=12):
        self.sessions = {}
        self.max_history = max_history

    def get_history(self, chat_id):
        return self.sessions.get(chat_id, [])

    def add_message(self, chat_id, role, content):

        if chat_id not in self.sessions:
            self.sessions[chat_id] = []

        history = self.sessions[chat_id]

        history.append({
            "role": role,
            "content": content
        })

        self.sessions[chat_id] = history[-self.max_history:]

    def clear(self, chat_id):
        self.sessions.pop(chat_id, None)

    def clear_all(self):
        self.sessions.clear()

    def get_contacts(self):
        return list(self.sessions.keys())
