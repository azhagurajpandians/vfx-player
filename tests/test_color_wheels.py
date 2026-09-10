import sys
import unittest
from PyQt6 import QtWidgets

app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)

from gui.color_wheels_widget import ColorWheelWidget, SingleGradeWheelUnit, ColorGradingPanel


class TestColorWheelsWidget(unittest.TestCase):
    def setUp(self):
        self.panel = ColorGradingPanel()

    def test_default_neutral_parameters(self):
        slope, offset, power, sat = self.panel.get_cdl_parameters()
        # Default neutral values
        self.assertAlmostEqual(slope[0], 1.0, places=2)
        self.assertAlmostEqual(slope[1], 1.0, places=2)
        self.assertAlmostEqual(slope[2], 1.0, places=2)

        self.assertAlmostEqual(offset[0], 0.0, places=2)
        self.assertAlmostEqual(offset[1], 0.0, places=2)
        self.assertAlmostEqual(offset[2], 0.0, places=2)

        self.assertAlmostEqual(power[0], 1.0, places=2)
        self.assertAlmostEqual(power[1], 1.0, places=2)
        self.assertAlmostEqual(power[2], 1.0, places=2)

        self.assertAlmostEqual(sat, 1.0, places=2)

    def test_wheel_balance_rgb_conversion(self):
        wheel_unit = SingleGradeWheelUnit("TestWheel", default_master=1.0)
        # Shift towards red (x=1.0, y=0.0)
        wheel_unit.wheel.set_balance(1.0, 0.0)
        dr, dg, db = wheel_unit.get_rgb_delta()
        self.assertAlmostEqual(dr, 1.0, places=3)
        self.assertAlmostEqual(dg, -0.5, places=3)
        self.assertAlmostEqual(db, -0.5, places=3)

    def test_warmer_slider_adjusts_temperature(self):
        # Set Warmer to +1.0 (warmer shifts red up and blue down)
        self.panel.slider_warmer.setValue(1.0)
        slope, offset, power, sat = self.panel.get_cdl_parameters()
        self.assertGreater(slope[0], slope[2])  # Red slope > Blue slope

    def test_greener_slider_adjusts_tint(self):
        # Set Greener to +1.0
        self.panel.slider_greener.setValue(1.0)
        slope, offset, power, sat = self.panel.get_cdl_parameters()
        self.assertGreater(slope[1], slope[0])  # Green slope > Red slope

    def test_reset_all_returns_to_neutral(self):
        self.panel.slider_contrast.setValue(1.5)
        self.panel.slider_warmer.setValue(0.8)
        self.panel.slider_sat.setValue(2.2)
        self.panel.wheel_gain.set_master_value(2.0)
        self.panel.wheel_lift.set_master_value(0.3)

        self.panel.reset_all()

        slope, offset, power, sat = self.panel.get_cdl_parameters()
        self.assertAlmostEqual(slope[0], 1.0, places=2)
        self.assertAlmostEqual(slope[1], 1.0, places=2)
        self.assertAlmostEqual(slope[2], 1.0, places=2)
        self.assertAlmostEqual(offset[0], 0.0, places=2)
        self.assertAlmostEqual(power[0], 1.0, places=2)
        self.assertAlmostEqual(sat, 1.0, places=2)

    def test_wheel_custom_radius_and_scaling(self):
        wheel = ColorWheelWidget(wheel_radius=40)
        self.assertEqual(wheel.wheel_radius, 40)
        self.assertGreater(wheel.width(), 80)
        self.assertLessEqual(wheel.width(), 95)
        self.assertEqual(wheel.norm_x, 0.0)
        self.assertEqual(wheel.norm_y, 0.0)

    def test_wheel_emit_signal_flag(self):
        wheel = ColorWheelWidget(wheel_radius=40)
        emitted = []
        wheel.balance_changed.connect(lambda x, y: emitted.append((x, y)))

        # Silent update
        wheel.set_balance(0.5, -0.5, emit_signal=False)
        self.assertEqual(len(emitted), 0)
        self.assertAlmostEqual(wheel.norm_x, 0.5)
        self.assertAlmostEqual(wheel.norm_y, -0.5)

        # Emitting update
        wheel.set_balance(0.2, 0.3, emit_signal=True)
        self.assertEqual(len(emitted), 1)
        self.assertAlmostEqual(emitted[0][0], 0.2)
        self.assertAlmostEqual(emitted[0][1], 0.3)

    def test_wheel_reset_balance(self):
        wheel = ColorWheelWidget(wheel_radius=40)
        wheel.set_balance(0.8, -0.4)
        self.assertNotEqual(wheel.norm_x, 0.0)
        wheel.reset_balance()
        self.assertEqual(wheel.norm_x, 0.0)
        self.assertEqual(wheel.norm_y, 0.0)


if __name__ == '__main__':
    unittest.main()
