import sys

from PySide6.QtWidgets import QApplication
from ui.window import ReyetteWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = ReyetteWindow()
    window.showMaximized()

    sys.exit(app.exec())