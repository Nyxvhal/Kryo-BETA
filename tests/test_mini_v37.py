"""Native topmost contract tests with mocked Win32; not a Windows GUI test."""
import ctypes
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from kryonyx.main import DesktopApi, MiniApi

class MiniTopmost37Tests(TestCase):
 def setUp(self):
  self.d=DesktopApi.__new__(DesktopApi)
  self.d._mini=SimpleNamespace(native=SimpleNamespace(Handle=SimpleNamespace(ToInt64=lambda:0x12345678ABC)))
  self.d._mini_pin_at=0
 def test_dotnet_pointer_width_preserved(self):
  with patch('kryonyx.main.os.name','nt'):
   self.assertEqual(self.d._mini_hwnd(),0x12345678ABC)
 def test_integer_handle(self):
  self.d._mini.native=SimpleNamespace(hwnd=124)
  with patch('kryonyx.main.os.name','nt'):self.assertEqual(self.d._mini_hwnd(),124)
 def test_non_windows_does_not_invoke_native(self):
  with patch('kryonyx.main.os.name','posix'):self.assertFalse(self.d._pin_mini())
 def test_topmost_uses_no_move_no_size_no_activate_async(self):
  fn=Mock(return_value=1)
  user=SimpleNamespace(SetWindowPos=fn)
  with patch('kryonyx.main.os.name','nt'),patch.object(ctypes,'windll',SimpleNamespace(user32=user),create=True):
   self.assertTrue(self.d._pin_mini(force=True))
   args=fn.call_args.args
   self.assertEqual(args[0].value,0x12345678ABC)
   self.assertEqual(args[1].value,ctypes.c_void_p(-1).value)
   self.assertEqual(args[-1],0x4013)
   self.assertTrue(self.d._pin_mini())
   self.assertEqual(fn.call_count,1)
   self.d._pin_mini(force=True)
   self.assertEqual(fn.call_count,2)
 def test_failed_pin_can_retry(self):
  fn=Mock(side_effect=[0,1]);user=SimpleNamespace(SetWindowPos=fn)
  with patch('kryonyx.main.os.name','nt'),patch.object(ctypes,'windll',SimpleNamespace(user32=user),create=True):
   self.assertFalse(self.d._pin_mini())
   self.assertTrue(self.d._pin_mini())
   self.assertEqual(fn.call_count,2)
 def test_missing_window_is_safe(self):
  self.d._mini=None
  with patch('kryonyx.main.os.name','nt'):self.assertFalse(self.d._pin_mini(force=True))
 def test_open_existing_window_reasserts_topmost(self):
  self.d._pin_mini=Mock(return_value=True)
  self.assertTrue(self.d.mini_open());self.d._pin_mini.assert_called_once_with(force=True)
 def test_state_heartbeat_reasserts_topmost(self):
  self.d._mini_state={'loading':True};self.d._pin_mini=Mock()
  self.assertEqual(MiniApi(self.d).state(),{'loading':True})
  self.d._pin_mini.assert_called_once()
 def test_resize_reasserts_topmost(self):
  self.d._mini.resize=Mock();self.d._pin_mini=Mock()
  self.assertEqual(MiniApi(self.d).resize(440,190),{'width':440,'height':190})
  self.d._pin_mini.assert_called_once_with(force=True)
 def test_close_resets_pin_state(self):
  self.d._mini.destroy=Mock();self.d._mini_pin_at=123
  mini=self.d._mini;self.assertTrue(self.d.mini_close())
  mini.destroy.assert_called_once();self.assertIsNone(self.d._mini);self.assertEqual(self.d._mini_pin_at,0)

class MiniMove38Tests(TestCase):
 def test_drag_moves_only_the_mini_and_reasserts_topmost(self):
  mini=SimpleNamespace(x=100,y=80,move=Mock())
  desk=SimpleNamespace(_mini=mini,_pin_mini=Mock())
  self.assertTrue(MiniApi(desk).move_by(50,-30));mini.move.assert_called_once_with(150,50);desk._pin_mini.assert_called_once_with(force=True)
 def test_invalid_and_extreme_deltas_are_bounded(self):
  mini=SimpleNamespace(x=0,y=0,move=Mock());desk=SimpleNamespace(_mini=mini,_pin_mini=Mock())
  self.assertTrue(MiniApi(desk).move_by(100000,-100000));mini.move.assert_called_with(4096,-4096)
  # v73: junk is a zero step — nothing moves, the gesture goes on.
  self.assertTrue(MiniApi(desk).move_by('not a number',None));self.assertEqual(mini.move.call_count,1)
  self.assertTrue(MiniApi(desk).move_by(float('nan'),float('inf')));self.assertEqual(mini.move.call_count,1)
 def test_closed_window_cannot_move_main_window(self):
  self.assertFalse(MiniApi(SimpleNamespace(_mini=None)).move_by(5,5))


class MiniMove73Tests(TestCase):
 """v73: «мини-плеер не перемещается» — fractional deltas and display scaling."""
 def test_fractional_deltas_add_up_instead_of_being_dropped(self):
  # 150 % scaling: one device pixel is 0.67 CSS px. int() used to drop every step.
  mini=SimpleNamespace(x=100,y=80,move=Mock());desk=SimpleNamespace(_mini=mini,_pin_mini=Mock())
  api=MiniApi(desk)
  for _ in range(6):self.assertTrue(api.move_by(0.67,0.67))
  self.assertEqual(mini.move.call_args[0],(104,84))
 def test_position_is_exact_for_the_whole_gesture(self):
  # The window object may report a stale or truncated x; the gesture keeps its own.
  mini=SimpleNamespace(x=100,y=80,move=Mock());desk=SimpleNamespace(_mini=mini,_pin_mini=Mock())
  api=MiniApi(desk)
  api.move_by(10,0);mini.x=0                      # a stale read must not matter
  api.move_by(10,5)
  self.assertEqual(mini.move.call_args[0],(120,85))
 def test_new_gesture_reads_the_window_again(self):
  mini=SimpleNamespace(x=100,y=80,move=Mock());desk=SimpleNamespace(_mini=mini,_pin_mini=Mock())
  api=MiniApi(desk);api.move_by(10,0)
  desk._mini_drag_at-=5;mini.x=500;mini.y=300
  api.move_by(1,1);self.assertEqual(mini.move.call_args[0],(501,301))
 def test_native_path_is_preferred_and_not_pinned_every_step(self):
  mini=SimpleNamespace(x=0,y=0,move=Mock())
  desk=SimpleNamespace(_mini=mini,_pin_mini=Mock(),_native_move_mini=Mock(return_value=True))
  self.assertTrue(MiniApi(desk).move_by(2.5,-1.25))
  desk._native_move_mini.assert_called_once_with(2.5,-1.25);mini.move.assert_not_called()
  desk._pin_mini.assert_called_once_with()
 def test_carry_keeps_sub_pixel_rest(self):
  from kryonyx.main import _carry
  rest=0.0;moved=0
  for _ in range(3):
   step,rest=_carry(rest,0.67,1.5);moved+=step
  self.assertEqual(moved,3);self.assertAlmostEqual(rest,0.015,places=6)
  step,rest=_carry(0.0,1,1.25);self.assertEqual(step,1);self.assertAlmostEqual(rest,.25)
 def test_native_move_uses_window_rect_and_dpi(self):
  d=DesktopApi.__new__(DesktopApi);d._mini=object();d._mini_rest=(0.0,0.0)
  d._mini_hwnd=lambda:0x1234
  calls={}
  class User:
   class _Fn:
    def __init__(s,fn):s.fn=fn;s.argtypes=None;s.restype=None
    def __call__(s,*a):return s.fn(*a)
   def __init__(s):
    def rect(hwnd,ref):
     r=ref._obj;r.left,r.top,r.right,r.bottom=1000,600,1630,870;return 1
    s.GetWindowRect=User._Fn(rect)
    s.GetDpiForWindow=User._Fn(lambda hwnd:144)
    def pos(*a):calls['pos']=a;return 1
    s.SetWindowPos=User._Fn(pos)
  with patch('kryonyx.main.os.name','nt'),patch.object(ctypes,'windll',SimpleNamespace(user32=User()),create=True):
   self.assertTrue(d._native_move_mini(10,-4))
  # 150 %: 10 CSS px → 15 device px, −4 → −6; size and z-order untouched.
  self.assertEqual(calls['pos'][2:6],(1015,594,0,0))
  self.assertEqual(calls['pos'][6],0x0001|0x0004|0x0010)
