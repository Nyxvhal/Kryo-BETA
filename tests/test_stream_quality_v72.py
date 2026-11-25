"""v72 sound quality: Best / Balanced / Data saver choose the source format, every cached object remembers
the tier, codec and bitrate it was fetched with, a higher mode replaces a lower-tier copy on the next play
(the lower copy stays as the offline fallback), and the player can ask what is really playing."""
import asyncio, io, json, os, sqlite3, tempfile, unittest, wave
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestServer, TestClient
from kryonyx import audio_quality, audiocache, audiovault as v, server


class Selection(unittest.TestCase):
    rates = [{'abr': 48}, {'abr': 70}, {'abr': 128}, {'abr': 160}, {'abr': 256}]

    def pick(self, mode):
        with patch.object(audio_quality, 'mode', return_value=mode):
            return audio_quality.pick(self.rates, lambda x: x['abr'] * 1000)['abr'], audio_quality.format_selector()

    def test_best_takes_the_highest_bitrate(self):
        self.assertEqual(self.pick('best'), (256, 'bestaudio/best'))

    def test_balanced_and_data_saver_cap_the_bitrate(self):
        self.assertEqual(self.pick('balanced')[0], 160)
        self.assertIn('abr<=160', self.pick('balanced')[1])
        self.assertEqual(self.pick('data')[0], 70)
        self.assertIn('abr<=80', self.pick('data')[1])

    def test_data_saver_takes_the_lowest_available_when_nothing_fits(self):
        with patch.object(audio_quality, 'mode', return_value='data'):
            self.assertEqual(audio_quality.pick([{'abr': 256}], lambda x: x['abr'] * 1000)['abr'], 256)

    def test_unknown_setting_falls_back_to_best(self):
        with patch('kryonyx.storage.get_settings', return_value={'audioQuality': 'lossless'}):
            self.assertEqual(audio_quality.mode(), 'best')


class Labels(unittest.TestCase):
    def test_bitrate_units(self):
        self.assertEqual(server._kbps(160), 160)
        self.assertEqual(server._kbps(129_475), 129)
        self.assertIsNone(server._kbps('n/a'))
        self.assertIsNone(server._kbps(0))
        self.assertEqual(audiocache._quality_meta({'bitrate': 160_000, 'codec': 'opus', 'source_id': 'yt:a'}),
                         {'codec': 'opus', 'kbps': 160, 'source': 'yt:a'})

    def test_codec_names(self):
        self.assertEqual(server._codec_label('opus', None), 'Opus')
        self.assertEqual(server._codec_label('mp4a.40.2', None), 'AAC')
        self.assertEqual(server._codec_label(None, 'audio/webm; codecs=opus'), 'Opus')
        self.assertEqual(server._codec_label(None, 'audio/mpeg'), 'MP3')
        self.assertIsNone(server._codec_label(None, 'application/octet-stream'))


class VaultTiers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(v, 'cache_dir', return_value=self.tmp.name); self.p.start()

    def tearDown(self):
        self.p.stop(); self.tmp.cleanup()

    def store(self, tid, **kw):
        part = Path(self.tmp.name) / 'q.part'; part.write_bytes(b'q' * 30000)
        return v.store(tid, str(part), 'audio/webm', **kw)

    def test_tier_codec_and_bitrate_are_kept(self):
        token = self.store('a', tier='data', meta={'codec': 'opus', 'kbps': 70, 'source': 'yt:a', 'junk': 1})
        doc = v.info(token)
        self.assertEqual((doc['tier'], doc['codec'], doc['kbps'], doc['source']), ('data', 'opus', 70, 'yt:a'))
        self.assertNotIn('junk', doc)
        self.assertTrue(v.tier_ok(token, 'data'))
        self.assertFalse(v.tier_ok(token, 'balanced'))
        self.assertFalse(v.tier_ok(token, 'best'))

    def test_higher_tier_satisfies_lower_modes(self):
        token = self.store('b', tier='best')
        self.assertTrue(all(v.tier_ok(token, m) for m in ('data', 'balanced', 'best')))

    def test_vault_from_v71_gains_the_column_and_counts_as_best(self):
        folder = v.folder(); os.makedirs(folder, exist_ok=True)
        db = sqlite3.connect(os.path.join(folder, 'audio-vault.sqlite'))
        db.execute('CREATE TABLE audio (key TEXT PRIMARY KEY,mime TEXT NOT NULL,size INTEGER NOT NULL,touched REAL NOT NULL,data BLOB NOT NULL)')
        db.execute('INSERT INTO audio VALUES(?,?,?,?,?)', (v.key('old'), 'audio/mpeg', 5, 1.0, b'12345'))
        db.commit(); db.close()
        token = v.find('old')
        self.assertIsNotNone(token)
        self.assertIsNone(v.info(token)['tier'])
        self.assertTrue(v.tier_ok(token, 'best'))
        self.assertIsNotNone(self.store('new', tier='balanced'))

    def test_forget_drops_one_object(self):
        self.store('c'); self.store('d')
        self.assertEqual(v.forget('c'), 1)
        self.assertIsNone(v.find('c')); self.assertIsNotNone(v.find('d'))


class QualityHTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(v, 'cache_dir', return_value=self.tmp.name); self.p.start()
        self.mode = 'data'; self.calls = 0; self.offline = False
        self.q = patch.object(audio_quality, 'mode', side_effect=lambda: self.mode); self.q.start()
        b = io.BytesIO()
        with wave.open(b, 'wb') as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(b'\0\1' * 22050 * 2)
        self.data = b.getvalue()

        async def upstream(req):
            self.calls += 1
            return web.Response(body=self.data, headers={'Content-Type': 'audio/wav'})
        app = web.Application(); app.router.add_get('/audio', upstream)
        self.up = TestServer(app); await self.up.start_server()

        async def media(track_id, *a, **kw):
            if self.offline:
                raise RuntimeError('source unreachable')
            kbps = {'data': 70, 'balanced': 160, 'best': 256}[self.mode]
            return track_id, {'url': str(self.up.make_url('/audio')), 'mime': 'audio/wav', 'tier': self.mode,
                              'codec': 'opus', 'bitrate': kbps * 1000, 'source_id': track_id}
        self.r = patch.object(server, '_media_for', side_effect=media); self.r.start()
        self.client = TestClient(TestServer(server.build_app())); await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close(); await self.up.close()
        self.r.stop(); self.q.stop(); self.p.stop(); self.tmp.cleanup()

    async def play(self, tid, query=''):
        r = await self.client.get(f'/api/stream?id={tid}{query}')
        body = await r.read()
        return r, body

    async def committed(self, tid, tier):
        for _ in range(200):
            token = v.find(tid)
            if token and (v.info(token) or {}).get('tier') == tier:
                return token
            await asyncio.sleep(.01)
        self.fail(f'{tid} was not cached as {tier}')

    async def info(self, tid, dur=''):
        r = await self.client.get(f'/api/stream/info?id={tid}' + (f'&dur={dur}' if dur else ''))
        self.assertEqual(r.status, 200)
        return await r.json()

    async def test_cached_object_reports_what_is_really_stored(self):
        r, body = await self.play('t1'); self.assertEqual(body, self.data)
        await self.committed('t1', 'data')
        doc = await self.info('t1', 2)
        self.assertTrue(doc['cached']); self.assertEqual(doc['tier'], 'data')
        self.assertEqual((doc['codec'], doc['kbps'], doc['satisfies']), ('Opus', 70, True))

    async def test_higher_mode_replaces_a_lower_copy_on_next_play(self):
        await self.play('t2'); await self.committed('t2', 'data'); before = self.calls
        self.mode = 'best'
        doc = await self.info('t2')
        self.assertFalse(doc['satisfies'])
        r = await self.client.post('/api/stream/requality', json={'id': 't2'})
        self.assertTrue((await r.json())['reload'])
        r, body = await self.play('t2')
        self.assertEqual(body, self.data)
        self.assertGreater(self.calls, before, 'a fresh stream was requested')
        token = await self.committed('t2', 'best')
        self.assertEqual(v.info(token)['kbps'], 256)
        r = await self.client.post('/api/stream/requality', json={'id': 't2'})
        self.assertFalse((await r.json())['reload'])

    async def test_lower_copy_still_plays_offline_and_on_request(self):
        await self.play('t3'); await self.committed('t3', 'data')
        self.mode = 'best'; self.offline = True; before = self.calls
        r, body = await self.play('t3')
        self.assertEqual((r.status, body), (200, self.data))
        r, body = await self.play('t3', '&q=any')
        self.assertEqual((r.status, body), (200, self.data))
        self.assertEqual(self.calls, before)

    async def test_lower_mode_reuses_a_better_copy(self):
        self.mode = 'best'; await self.play('t4'); await self.committed('t4', 'best'); before = self.calls
        self.mode = 'data'
        r, body = await self.play('t4')
        self.assertEqual(body, self.data); self.assertEqual(self.calls, before)
        self.assertEqual(r.headers.get('X-Kryonyx-Cache'), 'hit')

    async def test_info_requires_an_id_and_never_resolves(self):
        r = await self.client.get('/api/stream/info')
        self.assertEqual(r.status, 400)
        doc = await self.info('never-played', 5)
        self.assertFalse(doc['cached']); self.assertIsNone(doc['kbps'])
        self.assertEqual(self.calls, 0)


if __name__ == '__main__':
    unittest.main()
