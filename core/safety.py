
class SafetyEngine:

    BLOCKED_PATTERNS = [
        "password",
        "otp",
        "one time password",
        "kode verifikasi",
        "kode otp"
    ]

    MAX_RESPONSE_LENGTH = 1500

    def validate(self, message, response):

        if not response:
            return False

        if len(response) > self.MAX_RESPONSE_LENGTH:
            return False

        if len(response.strip()) == 0:
            return False

        # Jangan membalas permintaan informasi
        # autentikasi atau kredensial.
        normalized = message.lower()

        if any(
            word in normalized
            for word in self.BLOCKED_PATTERNS
        ):
            return False

        return True
