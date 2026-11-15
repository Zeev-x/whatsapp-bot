from abc import ABC, abstractmethod


class ReplyAdapter(ABC):

    @abstractmethod
    def send(self, chat_id, message):
        pass