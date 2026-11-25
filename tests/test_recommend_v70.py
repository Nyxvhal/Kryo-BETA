"""v70 recommendation quality contracts; offline, no external services."""
import asyncio, tempfile, time, unittest, warnings
from unittest.mock import AsyncMock, patch
from kryonyx import recommend as r, storage, trackmeta, providers


def track(i, artist='Artist', title=None, source='youtube', duration=200):
    return {'id': f'yt:{i}', 'title': title or f'Song {i}', 'artist': artist, 'source': source, 'duration': duration}


class Quality70(unittest.TestCase):
    def test_junk_rejected_in_strict_mode(self):
        for title in ['новинки музыки 2026', 'Хиты 2026 🔥 лучшие песни', 'Top 50 songs', '1 hour lofi', 'Podcast #12', 'Song (sped up)']:
            with self.subTest(title=title):
                self.assertTrue(r._quality({'title': title, 'artist': 'A'}, strict=True)[1])

    def test_normal_songs_pass_and_versions_only_penalised(self):
        self.assertEqual(r._quality({'title': 'Night Song', 'artist': 'CG5', 'duration': 200}), (0.0, False))
        penalty, reject = r._quality({'title': 'Night Song (slowed + reverb)', 'artist': 'CG5'})
        self.assertFalse(reject); self.assertGreater(penalty, 0)
        self.assertEqual(r._quality({'title': 'Night Song (slowed)', 'artist': 'CG5'}, allow_derived=True), (0.0, False))

    def test_snippets_sink_and_long_mixes_are_never_recommended(self):
        self.assertTrue(r._quality({'title': 'Song', 'artist': 'A', 'duration': 30}, strict=True)[1])
        short = r._quality({'title': 'Song', 'artist': 'A', 'duration': 30})
        self.assertFalse(short[1]); self.assertGreaterEqual(short[0], 2.0)
        self.assertTrue(r._quality({'title': 'Song', 'artist': 'A', 'duration': 3 * 3600})[1])

    def test_placeholder_artist_rejected_only_when_strict(self):
        self.assertTrue(r._quality({'title': 'Song', 'artist': 'YouTube Music'}, strict=True)[1])
        self.assertFalse(r._quality({'title': 'Song', 'artist': 'YouTube Music'})[1])

    def test_versions_of_one_song_share_identity(self):
        base = r._identity2({'artist': 'Artist feat. Guest', 'title': 'Song (Official Video)'})
        for title in ['Song', 'Song (sped up)', 'Song - Remastered 2011', 'Song [Lyric Video]', 'Song (feat. Guest)']:
            with self.subTest(title=title):
                self.assertEqual(r._identity2({'artist': 'Artist', 'title': title}), base)
        self.assertNotEqual(r._identity2({'artist': 'Artist', 'title': 'Song Part 2'}), base)
        self.assertEqual(r._identity2({'artist': 'A', 'title': '(I Can’t Get No) Satisfaction'})[1], r._norm('(I Can’t Get No) Satisfaction'))

    def test_score_dedupes_versions_and_strict_keeps_catalog_tracks(self):
        tracks = [track(1, title='Song'), track(2, title='Song (sped up)'), track(3, 'B', 'новинки музыки 2026'),
                  {**track(4, 'YouTube Music', 'Chart song'), 'recommend_basis': 'chart'}]
        with patch.object(r.storage, 'get_settings', return_value={}), patch.object(r, '_external', return_value={'artists': [], 'played': set(), 'liked': set(), 'queries': []}):
            out = r._score(tracks, {}, set(), set(), strict=True)
        self.assertEqual([t['id'] for t in out], ['yt:1', 'yt:4'])

    def test_spaced_avoids_back_to_back_artists(self):
        items = [track(i, 'A' if i < 4 else 'B') for i in range(6)]
        out = [t['artist'] for t in r._spaced(items)]
        self.assertEqual(out[:4], ['A', 'B', 'A', 'B'])
        self.assertEqual(len(out), 6)

    def test_editorial_pick_prefers_exact_and_skips_regional(self):
        cards = [{'id': 'ytplaylist:1', 'title': 'Indian Indie Hits 2023', 'artist': 'YouTube Music'},
                 {'id': 'ytplaylist:2', 'title': 'Indie Anthems', 'artist': 'YouTube Music'},
                 {'id': 'ytplaylist:3', 'title': 'Indie Mix', 'artist': 'Some User'}]
        picks = r._pick_editorial(cards, {'prefer': ('indie anthems',), 'keys': ('indie',)})
        self.assertEqual([c['id'] for c in picks], ['ytplaylist:2'])

    def test_clip_titles_lose_promo_but_keep_versions(self):
        clean = lambda title, artist: trackmeta.clean_track({'title': title, 'artist': artist})['title']
        self.assertEqual(clean('SQWOZ BAB, Satyr – СКИНЬ НОЖКИ (Премьера клипа 2026)', 'SQWOZ BAB'), 'СКИНЬ НОЖКИ')
        self.assertEqual(clean('Song (Official Music Video 2026)', 'Band'), 'Song')
        self.assertEqual(clean('Song (Live)', 'Band'), 'Song (Live)')
        self.assertEqual(clean('Bandit - Song', 'Band'), 'Bandit - Song')


class Bounded70(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_waiter_closes_coroutine(self):
        async def never():
            await asyncio.sleep(10)
        holders = [asyncio.ensure_future(r._bounded(asyncio.sleep(1))) for _ in range(4)]
        await asyncio.sleep(0)
        coro = never()
        waiter = asyncio.ensure_future(r._bounded(coro))
        await asyncio.sleep(0)
        waiter.cancel()
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            with self.assertRaises(asyncio.CancelledError):
                await waiter
        self.assertIsNone(coro.cr_frame)  # closed, never awaited warning impossible
        for h in holders:
            h.cancel()
        await asyncio.gather(*holders, return_exceptions=True)

    async def test_failure_is_empty_list(self):
        async def boom():
            raise OSError('offline')
        self.assertEqual(await r._bounded(boom()), [])


class Storage70(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); storage._local.conn = None; storage.init(self.tmp.name + '/t.db')

    def tearDown(self):
        storage._local.conn.close(); storage._local.conn = None; self.tmp.cleanup()

    def test_taste_decays_with_time(self):
        storage._bump_taste('Old', 10)
        storage._conn().execute("UPDATE artist_taste SET updated_at=? WHERE artist='Old'", (time.time() - storage.TASTE_HALF_LIFE,)); storage._conn().commit()
        storage._bump_taste('New', 6)
        top = storage.top_artists(5)
        self.assertEqual(top[0]['artist'], 'New'); self.assertAlmostEqual(top[1]['weight'], 5, places=1)

    def test_skip_without_duration_after_long_listen_is_not_fast_skip(self):
        storage.log_play({'id': 'yt:a', 'title': 'Song', 'artist': 'A'}, 200, False, True)
        self.assertEqual(storage.disliked_artists(), [])
        self.assertGreater(storage.top_artists(1, min_weight=0)[0]['weight'], 0)
        storage.log_play({'id': 'yt:b', 'title': 'Other', 'artist': 'B'}, 3, False, True)
        row = storage._conn().execute("SELECT weight, skips FROM artist_taste WHERE artist='B'").fetchone()
        self.assertLess(row['weight'], 0); self.assertEqual(row['skips'], 1)

    def test_played_ids_are_most_recent(self):
        for i in range(5):
            storage.log_play({'id': f'yt:{i}', 'title': str(i), 'artist': 'A'}, 40)
        storage.log_play({'id': 'yt:0', 'title': '0', 'artist': 'A'}, 40)
        self.assertEqual(storage.played_ids(2), {'yt:0', 'yt:4'})

    def test_top_tracks_counts_real_listens_per_session(self):
        t = {'id': 'yt:r', 'title': 'Repeat', 'artist': 'A'}
        for session in ('s1', 's2', 's3'):
            storage.log_play(t, 120, True, False, session)
        storage.log_play({'id': 'yt:s', 'title': 'Skipped', 'artist': 'B'}, 3, False, True, 's4')
        storage.log_play({'id': 'yt:s', 'title': 'Skipped', 'artist': 'B'}, 3, False, True, 's5')
        top = storage.top_tracks(30, 10)
        self.assertEqual([x['id'] for x in top], ['yt:r']); self.assertEqual(top[0]['listens'], 3)

    def test_recent_activity_marks_fast_skips(self):
        storage.log_play({'id': 'yt:s', 'title': 'Skipped', 'artist': 'B'}, 3, False, True)
        activity = storage.recent_activity()
        self.assertEqual(activity['skips'], {'yt:s': 1}); self.assertIn('yt:s', activity['played'])


class Rows70(unittest.IsolatedAsyncioTestCase):
    def ctx(self, temp, **extra):
        values = dict(top_artists=[], recent_seed_tracks=[], played_ids=set(), disliked_artists=[], list_likes=[], history=[])
        values.update(extra)
        patches = [patch.object(r, 'cache_dir', return_value=temp), patch.object(r.extras, 'fill_thumbnails', AsyncMock()),
                   patch.object(r, '_collection_rows', AsyncMock(return_value=[])),
                   patch.object(r, '_external', return_value={'artists': [], 'played': set(), 'liked': set(), 'queries': []})]
        patches += [patch.object(r.storage, k, return_value=v) for k, v in values.items()]
        return patches

    async def run_rows(self, patches, limit=6):
        r.invalidate()
        for p in patches:
            p.start()
        try:
            return await r.build_rows(limit)
        finally:
            for p in reversed(patches):
                p.stop()
            r.invalidate()

    async def test_cold_start_uses_catalog_first_and_never_seo_search(self):
        catalog = [track(f'c{i}', f'Artist {i}') for i in range(30)]
        search = AsyncMock(return_value={'tracks': [track('junk', 'X', 'новинки музыки 2026')]})
        with tempfile.TemporaryDirectory() as temp:
            patches = self.ctx(temp) + [patch.object(r, '_user_sources', return_value=['youtube']), patch.object(r, '_curated', AsyncMock(return_value=catalog)),
                                        patch.object(r.providers, 'search', search), patch.object(r, '_lang', return_value='en')]
            rows = await self.run_rows(patches)
        self.assertTrue(rows)
        self.assertEqual(rows[0]['title_key'], 'Popular now'); self.assertEqual(rows[0]['subtitle_key'], 'Official chart')
        ids = [t['id'] for row in rows for t in row['items']]
        self.assertNotIn('yt:junk', ids); self.assertEqual(len(ids), len(set(ids)))
        search.assert_not_called()

    async def test_catalog_failure_falls_back_to_strict_search(self):
        async def search(q, **k):
            return {'tracks': [track(q + str(i), f'Artist {q}{i}') for i in range(12)] + [track(q + 'junk', 'X', 'Top 100 songs 2026')]}
        with tempfile.TemporaryDirectory() as temp:
            patches = self.ctx(temp) + [patch.object(r, '_user_sources', return_value=['youtube']), patch.object(r, '_curated', AsyncMock(return_value=[])),
                                        patch.object(r.providers, 'search', side_effect=search)]
            rows = await self.run_rows(patches)
        self.assertGreaterEqual(len(rows), 4)
        self.assertFalse([t for row in rows for t in row['items'] if 'junk' in t['id']])

    async def test_more_from_artist_contains_only_that_artist(self):
        top = [{'artist': 'Nightfall', 'weight': 10, 'plays': 3, 'skips': 0}]
        found = [track(i, 'Nightfall' if i % 2 else 'Imposter') for i in range(20)]
        with tempfile.TemporaryDirectory() as temp:
            patches = self.ctx(temp, top_artists=top) + [patch.object(r, '_search_many', AsyncMock(return_value=found)), patch.object(r, '_user_sources', return_value=['soundcloud'])]
            rows = await self.run_rows(patches, 4)
        more = next(row for row in rows if row.get('title_key') == 'More from {artist}')
        self.assertTrue(more['items']); self.assertEqual({t['artist'] for t in more['items']}, {'Nightfall'})

    async def test_artists_new_to_you_come_from_seed_radio(self):
        seed = track('seed', 'Known')
        related = [track(f'k{i}', 'Known') for i in range(6)] + [track(f'n{i}', f'New {i}') for i in range(8)]
        with tempfile.TemporaryDirectory() as temp:
            patches = self.ctx(temp, recent_seed_tracks=[seed], history=[seed]) + [patch.object(r.providers, 'related', AsyncMock(return_value=related)),
                                                                                  patch.object(r, '_search_many', AsyncMock(return_value=[])), patch.object(r, '_user_sources', return_value=['youtube']),
                                                                                  patch.object(r, '_cold_tracks', AsyncMock(return_value=[]))]
            rows = await self.run_rows(patches, 4)
        fresh = next(row for row in rows if row.get('title_key') == 'Artists new to you')
        artists = [t['artist'] for t in fresh['items']]
        self.assertNotIn('Known', artists); self.assertEqual(len(artists), len(set(artists)))

    async def test_daily_mix_is_stable_within_a_day(self):
        found = [track(i, f'Artist {i % 7}') for i in range(40)]
        with patch.object(r, '_top_artists', return_value=[{'artist': 'Artist 1', 'weight': 3}]), patch.object(r.storage, 'list_likes', return_value=[]), \
                patch.object(r.storage, 'recent_seed_tracks', return_value=[]), patch.object(r, '_search_many', AsyncMock(return_value=found)), \
                patch.object(r.storage, 'played_ids', return_value=set()), patch.object(r.storage, 'disliked_artists', return_value=[]), \
                patch.object(r.storage, 'get_settings', return_value={}), patch.object(r, '_external', return_value={'artists': [], 'played': set(), 'liked': set(), 'queries': []}):
            first = await r.daily_mix(20); second = await r.daily_mix(20)
        self.assertEqual([t['id'] for t in first['items']], [t['id'] for t in second['items']])
        artists = [t['artist'] for t in first['items']]
        self.assertFalse(any(a == b for a, b in zip(artists, artists[1:])))


class Related70(unittest.IsolatedAsyncioTestCase):
    async def test_non_youtube_seed_uses_matching_youtube_radio(self):
        twin = {'id': 'yt:twin', 'title': 'Song (Official Audio)', 'artist': 'Band', 'artists': [{'name': 'Band'}]}
        mix = [track(i, f'R{i}') for i in range(20)]
        providers._page_cache.clear() if hasattr(providers._page_cache, 'clear') else None
        with patch.object(providers.ytmusic, 'songs', AsyncMock(return_value=[{'id': 'yt:other', 'title': 'Song', 'artist': 'Cover Band'}, twin])), \
                patch.object(providers, 'youtube_mix', AsyncMock(return_value=mix)) as radio, patch.object(providers, 'search', AsyncMock(return_value={'tracks': []})):
            out = await providers.related('sc:abc', 'Band', 'Song', 20, sources=['youtube', 'soundcloud'])
        radio.assert_awaited_once_with('twin', 20); self.assertEqual(len(out), 20)

    async def test_no_twin_for_wrong_artist(self):
        with patch.object(providers.ytmusic, 'songs', AsyncMock(return_value=[{'id': 'yt:other', 'title': 'Song', 'artist': 'Someone'}])), \
                patch.object(providers, 'youtube_mix', AsyncMock(return_value=[])) as radio, patch.object(providers, 'search', AsyncMock(return_value={'tracks': []})):
            await providers.related('sc:zzz', 'Lonely Band', 'Unique Song', 20, sources=['youtube'])
        radio.assert_not_awaited()


if __name__ == '__main__':
    unittest.main()
