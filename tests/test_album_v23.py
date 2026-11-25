"""Desktop bridge allow-list: mini controls cannot execute arbitrary JS."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from kryonyx.main import MiniApi

class MiniBridge23Tests(unittest.TestCase):
 def setUp(self):
  self.desk=SimpleNamespace(_mini_state={},_eval_main=Mock(),show_window=Mock(),mini_close=Mock(),_mini=None)
  self.api=MiniApi(self.desk)
 def test_lyrics_and_queue_open_main_and_call_fixed_action(self):
  for name in ('lyrics','queue'):
   with self.subTest(name=name):
    self.assertTrue(self.api.action(name));self.assertIn('MiniPlayer.action("'+name+'")',self.desk._eval_main.call_args.args[0])
  self.assertEqual(self.desk.show_window.call_count,2)
 def test_unknown_action_cannot_run_script(self):
  self.assertFalse(self.api.action('lyrics");alert(1);//'));self.desk._eval_main.assert_not_called()
 def test_volume_is_clamped_not_interpolated_text(self):
  for value,expected in [(230,100.0),(-8,0.0),(31,31.0),('evil()',0.0)]:
   with self.subTest(value=value):
    self.assertTrue(self.api.volume(value));self.assertIn('MiniPlayer.volume('+repr(expected)+')',self.desk._eval_main.call_args.args[0])
 def test_seek_keeps_existing_limits(self):
  self.api.seek(4);self.assertIn('MiniPlayer.seek(1.0)',self.desk._eval_main.call_args.args[0])

 def test_return_to_player_opens_main_and_closes_mini_without_playback_command(self):
  self.assertTrue(self.api.action('show'))
  self.desk.show_window.assert_called_once()
  self.desk.mini_close.assert_called_once()
  code=self.desk._eval_main.call_args.args[0]
  self.assertNotIn('App.openNow()',code)
  self.assertIn('MiniPlayer.closed()',code)
  self.assertNotIn('KTray.act',code)
