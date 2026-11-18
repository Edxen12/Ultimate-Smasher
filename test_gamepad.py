import os
import unittest
from unittest.mock import Mock, call, mock_open, patch

from PyQt5 import sip
from PyQt5.QtCore import QCoreApplication, QEvent, Qt
from PyQt5.QtTest import QTest
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QVBoxLayout,
    QWidget,
)

import gamepad


class GamepadTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = QWidget()
        with patch.object(gamepad.Gamepad, "scan"), patch.object(gamepad, "open_xinput", return_value=None):
            self.pad = gamepad.Gamepad(self.window)
        self.pad.scanner.stop()
        self.pad.can_send = Mock(return_value=True)
        self.pad.send = Mock()
        self.first = self.add_device("pad", 42)

    def tearDown(self):
        if not sip.isdeleted(self.window):
            self.window.deleteLater()
            with patch.object(gamepad.os, "close"):
                QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)

    def add_device(self, path, fd):
        device = gamepad.Device(fd, Mock(), {0: (0, 255), 1: (0, 255)})
        self.pad.devs[path] = device
        return device

    def axis(self, device, code, value):
        self.pad.handle(device, gamepad.EV_ABS, code, value)

    def test_eof_disconnects_instead_of_spinning_notifier(self):
        with patch.object(gamepad.os, "read", return_value=b""), patch.object(gamepad.os, "close") as close:
            self.pad.read("pad")
        close.assert_called_once_with(42)
        self.assertFalse(self.pad.connected)
        self.first.notifier.setEnabled.assert_called_once_with(False)
        self.pad.send.assert_not_called()

    def test_axis_normalisation_at_rest_and_at_limits(self):
        self.first.ranges = dict.fromkeys(gamepad.STICK_AXES, (-32768, 32767))
        self.axis(self.first, 0, 0)
        self.axis(self.first, 1, 0)
        self.assertIsNone(self.pad.held)
        self.axis(self.first, 0, -32768)
        self.assertEqual(self.pad.held, (self.first, Qt.Key_Left))
        self.axis(self.first, 0, -1)
        self.assertIsNone(self.pad.held)
        self.pad.send.assert_called_once_with(Qt.Key_Left)

    def test_devices_do_not_share_axes_or_cancel_another_pads_repeat(self):
        second = self.add_device("pad2", 43)
        self.axis(self.first, 16, -1)
        self.axis(second, 1, 128)
        self.assertEqual(self.pad.held, (self.first, Qt.Key_Left))
        self.axis(second, 1, 0)
        self.assertEqual(self.pad.held, (second, Qt.Key_Up))
        changes = Mock()
        self.pad.connected_changed.connect(changes)
        with patch.object(gamepad.os, "close"):
            self.pad.drop("pad")
            self.assertEqual(self.pad.held, (second, Qt.Key_Up))
            changes.assert_not_called()
            self.pad.drop("pad2")
        self.assertIsNone(self.pad.held)
        self.assertFalse(self.pad.repeat.isActive())
        changes.assert_called_once_with(False)

    def test_reconnect_starts_with_neutral_axes(self):
        self.axis(self.first, 0, 255)
        changes = Mock()
        self.pad.connected_changed.connect(changes)
        with (
            patch.object(gamepad, "open", mock_open(read_data=""), create=True),
            patch.object(gamepad.os, "close") as close,
        ):
            self.pad.scan()
        self.first.notifier.setEnabled.assert_called_once_with(False)
        close.assert_called_once_with(42)
        changes.assert_called_once_with(False)
        second = self.add_device("pad", 42)
        self.axis(second, 1, 128)
        self.assertIsNone(self.pad.held)

    def test_window_destruction_closes_open_descriptor(self):
        self.window.deleteLater()
        with patch.object(gamepad.os, "close") as close:
            QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        close.assert_called_once_with(42)
        self.first.notifier.setEnabled.assert_called_once_with(False)

    def test_bumpers_emit_section_steps_without_typing(self):
        steps = Mock()
        self.pad.section_step.connect(steps)
        for code in (310, 311):
            for value in (1, 2, 0):
                self.pad.handle(self.first, gamepad.EV_KEY, code, value)
        self.assertEqual(steps.call_args_list, [call(-1), call(1)])
        self.pad.send.assert_not_called()

    @unittest.skipUnless(gamepad.fcntl is not None, "Linux evdev discovery")
    def test_scan_detects_controller_without_joydev(self):
        word, bit = divmod(gamepad.BTN_SOUTH, gamepad.KEY_WORD_BITS)
        bitmap = " ".join([f"{1 << bit:x}"] + ["0"] * word)
        virtual_keyboard_bitmap = " ".join([f"{(1 << gamepad.KEY_WORD_BITS) - 1:x}"] * (word + 1))
        devices = (
            f"H: Handlers=event0\nB: KEY={bitmap}\n\n"
            "H: Handlers=kbd event1\nB: KEY=8000 100 0 ff\n\n"
            f"H: Handlers=kbd event2\nB: KEY={virtual_keyboard_bitmap}\n"
        )
        with (
            patch.object(gamepad, "open", mock_open(read_data=devices), create=True),
            patch.object(gamepad.os, "open", return_value=39) as open_device,
            patch.object(gamepad.os, "close"),
            patch.object(gamepad, "axis_range", return_value=(0, 255)),
            patch.object(gamepad, "QSocketNotifier"),
        ):
            self.pad.scan()
        open_device.assert_called_once_with("/dev/input/event0", os.O_RDONLY | os.O_NONBLOCK)
        self.assertIn("/dev/input/event0", self.pad.devs)

    def test_xinput_ignores_buttons_held_at_connect_and_releases_on_unplug(self):
        self.pad.devs.clear()
        self.pad.xinput = Mock(side_effect=lambda slot: sample if slot == 0 else None)
        connected = Mock()
        self.pad.connected_changed.connect(connected)
        sample = (0x0010, 0, 0)  # Start is already held.
        self.pad.poll_xinput()
        self.pad.send.assert_not_called()

        sample = (0, 0, 0)
        self.pad.poll_xinput()
        sample = (0x1008, 0, 0)  # Right plus A.
        self.pad.poll_xinput()
        self.pad.poll_xinput()
        self.assertEqual(self.pad.send.call_args_list, [call(Qt.Key_Right), call(Qt.Key_Return, Qt.NoModifier)])

        sample = None
        self.pad.poll_xinput()
        self.assertIsNone(self.pad.held)
        self.assertFalse(self.pad.repeat.isActive())
        self.assertEqual(connected.call_args_list, [call(True), call(False)])

    def test_digital_dpad_repeats_and_releases(self):
        for value in (1, 2):
            self.pad.handle(self.first, gamepad.EV_KEY, gamepad.BTN_DPAD_DOWN, value)
        self.assertEqual(self.pad.held, (self.first, Qt.Key_Down))
        self.pad._repeat()
        self.pad.handle(self.first, gamepad.EV_KEY, gamepad.BTN_DPAD_DOWN, 0)
        self.assertIsNone(self.pad.held)
        self.assertFalse(self.pad.repeat.isActive())
        self.assertEqual(self.pad.send.call_args_list, [call(Qt.Key_Down), call(Qt.Key_Down)])

    def test_controls_stay_in_own_qt_window_and_popup(self):
        layout = QVBoxLayout(self.window)
        checkbox = QCheckBox("Check", self.window)
        combo = QComboBox(self.window)
        combo.addItems(["First", "Second"])
        layout.addWidget(checkbox)
        layout.addWidget(combo)
        del self.pad.can_send
        del self.pad.send
        self.window.show()
        self.window.activateWindow()
        QTest.qWait(20)
        checkbox.setFocus()
        self.pad.handle(self.first, gamepad.EV_KEY, gamepad.BTN_SOUTH, 1)
        self.assertTrue(checkbox.isChecked())
        combo.setFocus()
        self.pad.handle(self.first, gamepad.EV_KEY, gamepad.BTN_SOUTH, 1)
        self.assertIs(self.pad.receiver(), combo.view())
        steps = Mock()
        self.pad.section_step.connect(steps)
        self.pad.handle(self.first, gamepad.EV_KEY, 311, 1)
        steps.assert_not_called()
        self.pad.send(Qt.Key_Down)
        self.pad.handle(self.first, gamepad.EV_KEY, gamepad.BTN_SOUTH, 1)
        self.assertEqual(combo.currentIndex(), 1)
        self.assertIsNone(self.app.activePopupWidget())
        dialog = QDialog(self.window)
        dialog.setModal(True)
        dialog.show()
        self.assertIs(self.pad.receiver(), dialog)
        self.pad.send(Qt.Key_Escape)
        self.assertFalse(dialog.isVisible())
        other = QWidget()
        other.show()
        other.activateWindow()
        QTest.qWait(20)
        self.assertFalse(self.pad.can_send())
        other.close()

    def test_repeat_stops_when_window_can_no_longer_receive_keys(self):
        self.axis(self.first, 16, 1)
        self.pad.can_send.return_value = False
        self.pad._repeat()
        self.pad.send.assert_called_once_with(Qt.Key_Right)
        self.assertFalse(self.pad.repeat.isActive())
        self.assertIsNone(self.pad.held)

    def test_disabling_window_clears_held_input(self):
        self.axis(self.first, 16, 1)
        self.pad.can_send.return_value = False
        self.window.setEnabled(False)
        self.assertIsNone(self.first.direction())
        self.assertIsNone(self.pad.held)
        self.assertFalse(self.pad.repeat.isActive())

    def test_dropped_input_cancels_repeat_and_ignores_incomplete_batch(self):
        self.axis(self.first, 16, 1)
        self.pad.handle(self.first, gamepad.EV_SYN, gamepad.SYN_DROPPED, 0)
        self.assertFalse(self.pad.repeat.isActive())
        self.pad.handle(self.first, gamepad.EV_KEY, 304, 1)
        self.pad.send.assert_called_once_with(Qt.Key_Right)
        self.pad.handle(self.first, gamepad.EV_SYN, gamepad.SYN_REPORT, 0)
        self.axis(self.first, 17, -1)
        self.pad.send.assert_called_with(Qt.Key_Up)


if __name__ == "__main__":
    unittest.main()
