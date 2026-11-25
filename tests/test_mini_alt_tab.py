"""Mocked Win32 contract; an actual Windows shell test is still required."""
import ctypes
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from kryonyx.main import DesktopApi

class MiniToolWindowTests(TestCase):
 def setUp(self):
  self.d=DesktopApi.__new__(DesktopApi); self.d._mini=SimpleNamespace(native=SimpleNamespace(hwnd=0x12345678ABC)); self.d._mini_pin_at=0
 def test_styles_preserved_and_reapplied_for_new_handle(self):
  styles={0x12345678ABC:0x40000|0x8, 0x234:0x40000|0x8}
  get=Mock(side_effect=lambda h,i: styles[h.value])
  def put(h,i,v):
   old=styles[h.value]; styles[h.value]=v&0xffffffff; return old
  set_=Mock(side_effect=put); pos=Mock(return_value=1)
  with patch('kryonyx.main.os.name','nt'), patch.object(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(GetWindowLongW=get,SetWindowLongW=set_,SetWindowPos=pos)),create=True):
   self.assertTrue(self.d._pin_mini(force=True)); self.assertEqual(styles[0x12345678ABC],0x88); self.assertEqual(pos.call_args.args[-1],0x4033)
   self.assertTrue(self.d._pin_mini(force=True)); self.assertEqual(set_.call_count,1); self.assertEqual(pos.call_args.args[-1],0x4013)
   self.d._mini.native.hwnd=0x234; self.assertTrue(self.d._pin_mini(force=True)); self.assertEqual(styles[0x234],0x88)
 def test_zero_style_read_does_not_overwrite_window(self):
  get=Mock(return_value=0); set_=Mock(); pos=Mock(return_value=1)
  with patch('kryonyx.main.os.name','nt'), patch.object(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(GetWindowLongW=get,SetWindowLongW=set_,SetWindowPos=pos)),create=True):
   self.assertTrue(self.d._pin_mini(force=True));set_.assert_not_called();self.assertEqual(pos.call_args.args[-1],0x4013)
 def test_style_failure_does_not_break_topmost(self):
  pos=Mock(return_value=1)
  with patch('kryonyx.main.os.name','nt'),patch.object(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(SetWindowPos=pos)),create=True):
   self.assertTrue(self.d._pin_mini(force=True));self.assertEqual(pos.call_args.args[-1],0x4013)
