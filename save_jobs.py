"""Run file operations on Qt's worker pool and report their results."""
from PyQt5.QtCore import QObject, QRunnable, pyqtSignal


class SaveSignals(QObject):
    finished = pyqtSignal(object, object)


class DiskJob(QRunnable):
    def __init__(self, operation):
        super().__init__()
        self.operation = operation
        self.signals = SaveSignals()

    def run(self):
        try:
            result = self.operation()
        except Exception as error:  # noqa: BLE001 - worker boundary must always report failure to the GUI
            self.signals.finished.emit(None, error)
        else:
            self.signals.finished.emit(result, None)
