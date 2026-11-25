"""v72 search: the original recording first, covers/edits lower, copies of one recording collapsed,
three parallel YouTube Music queries with catalogue signals, stable pagination. No network."""
import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from kryonyx import providers, search_rank72 as r72, ytmusic


def song(i, title, artist, kind='song', **f):
    row = {'id': 'yt:' + i, 'title': title, 'artist': artist, 'artists': [{'name': a} for a in artist.split(', ')],
           'duration': f.pop('duration', 210), 'source': 'youtube', 'views': f.pop('views', None)}
    row['_rank72'] = {'kind': kind, **f}
    return row


class CoreTitle(unittest.TestCase):
    def test_promo_credit_and_remaster_tags_are_dropped(self):
        self.assertEqual(r72.core_title('Believer (Official Music Video)'), 'believer')
        self.assertEqual(r72.core_title('Get Lucky (feat. Pharrell Williams & Nile Rodgers)'), 'get lucky')
        self.assertEqual(r72.core_title('Bohemian Rhapsody - Remastered 2011'), 'bohemian rhapsody')
        self.assertEqual(r72.core_title('Numb [Official HD Video]'), 'numb')

    def test_version_words_match_word_starts_only(self):
        self.assertIn('sped', r72.versions('Believer (sped up)'))
        self.assertIn('cover', r72.versions('Believer - кавер на гитаре'))
        self.assertNotIn('live', r72.versions('Oliver Tree - Life Goes On'))
        self.assertEqual(r72.versions('Believer'), set())

    def test_play_counts(self):
        self.assertEqual(r72.plays('1.9M'), 1_900_000)
        self.assertEqual(r72.plays('7B'), 7_000_000_000)
        self.assertEqual(r72.plays('56K'), 56_000)
        self.assertEqual(r72.plays('1,234'), 1234)
        self.assertEqual(r72.plays(None), 0)


class Ranking(unittest.TestCase):
    def test_original_beats_covers_with_the_same_title(self):
        rows = [song('c1', 'Believer', 'Cover Nation', kind='ugc', vpos=0, views='2M'),
                song('c2', 'Believer (Piano Cover)', 'Piano Guy', kind='ugc', vpos=1),
                song('orig', 'Believer', 'Imagine Dragons', pos=0, top=True, views='1.9B'),
                song('sped', 'Believer (sped up)', 'Sped Hits', pos=1)]
        ids = [t['id'] for t in r72.rank('believer', rows)]
        self.assertEqual(ids[0], 'yt:orig')
        self.assertLess(ids.index('yt:orig'), ids.index('yt:c1'))
        self.assertGreater(ids.index('yt:sped'), ids.index('yt:orig'))

    def test_credited_title_is_still_the_exact_song(self):
        rows = [song('cover', 'Get Lucky', 'Karaoke Stars', kind='ugc', vpos=0),
                song('dp', 'Get Lucky (feat. Pharrell Williams & Nile Rodgers)', 'Daft Punk', pos=0, views='800M')]
        self.assertEqual(r72.rank('get lucky', rows)[0]['id'], 'yt:dp')

    def test_versions_win_when_the_query_asks_for_them(self):
        rows = [song('orig', 'Believer', 'Imagine Dragons', pos=0, top=True),
                song('sped', 'Believer (sped up)', 'Sped Hits', pos=3)]
        self.assertEqual(r72.rank('believer sped up', rows)[0]['id'], 'yt:sped')

    def test_copies_of_one_recording_collapse_to_the_catalogue_audio(self):
        rows = [song('video', 'Imagine Dragons - Believer (Official Music Video)', 'ImagineDragonsVEVO', kind='omv', vpos=0, views='2.6B'),
                song('audio', 'Believer', 'Imagine Dragons', pos=0)]
        ranked = r72.rank('imagine dragons believer', rows)
        self.assertEqual([t['id'] for t in ranked], ['yt:audio'])

    def test_artist_query_prefers_that_artists_songs(self):
        rows = [song('other', 'Rammstein', 'Some Band', pos=0),
                song('du', 'Du Hast', 'Rammstein', pos=2, top_artist_name='Rammstein')]
        self.assertEqual(r72.rank('rammstein', rows)[0]['id'], 'yt:du')

    def test_long_mixes_and_short_snippets_drop(self):
        rows = [song('mix', 'Believer', 'Imagine Dragons', kind='ugc', duration=3600, vpos=0),
                song('snip', 'Believer', 'Imagine Dragons Fan', kind='ugc', duration=30, vpos=1),
                song('orig', 'Believer', 'Imagine Dragons', pos=4)]
        self.assertEqual(r72.rank('believer', rows)[0]['id'], 'yt:orig')

    def test_public_hides_signals(self):
        self.assertNotIn('_rank72', r72.public(song('a', 'A', 'B')))


def item(vid, title, artist, result='song', category=None, video_type=None, views=None, duration='3:30'):
    out = {'videoId': vid, 'title': title, 'artists': [{'name': artist, 'id': 'UC' + vid}], 'resultType': result,
           'duration': duration, 'views': views}
    if category: out['category'] = category
    if video_type: out['videoType'] = video_type
    return out


class YTMusicSearch(unittest.IsolatedAsyncioTestCase):
    async def test_three_parallel_queries_and_catalogue_signals(self):
        calls = []

        async def fake(name, query, **kw):
            calls.append((name, query, kw.get('filter'), kw.get('ignore_spelling')))
            if kw.get('filter') == 'songs':
                return [item('orig', 'Believer', 'Imagine Dragons', video_type='MUSIC_VIDEO_TYPE_ATV', views='1.9B')] + \
                       [item(f's{i}', f'Song {i}', f'Artist {i}') for i in range(6)]
            if kw.get('filter') == 'videos':
                return [item('cover', 'Believer (Cover)', 'Cover Nation', result='video', video_type='MUSIC_VIDEO_TYPE_UGC', views='3M')]
            return [item('orig', 'Believer', 'Imagine Dragons', category='Top result', views='1.9B'),
                    {'resultType': 'artist', 'category': 'Top result', 'artist': 'Imagine Dragons'}]

        with patch.object(ytmusic, 'ready', return_value=True), patch.object(ytmusic, '_call', side_effect=fake):
            tracks = await ytmusic.search('believer', 25)
        kinds = sorted((c[2] or 'top', c[3]) for c in calls)
        self.assertEqual(kinds[:3], [('songs', True), ('top', False), ('videos', True)])
        orig = next(t for t in tracks if t['id'] == 'yt:orig')
        self.assertEqual(orig['_rank72']['kind'], 'song')
        self.assertTrue(orig['_rank72']['top'])
        self.assertEqual(orig['_rank72']['pos'], 0)
        self.assertEqual(orig['_rank72']['plays'], 1_900_000_000)
        self.assertEqual(orig['_rank72']['top_artist_name'], 'Imagine Dragons')
        self.assertEqual(next(t for t in tracks if t['id'] == 'yt:cover')['_rank72']['kind'], 'ugc')
        self.assertEqual(len({t['id'] for t in tracks}), len(tracks))

    async def test_weak_exact_songs_add_spelling_corrected_songs(self):
        calls = []

        async def fake(name, query, **kw):
            calls.append((kw.get('filter'), kw.get('ignore_spelling')))
            if kw.get('filter') == 'songs' and kw.get('ignore_spelling'):
                return [item('x', 'Something else', 'Nobody')]
            if kw.get('filter') == 'songs':
                return [item('fixed', 'Believer', 'Imagine Dragons')]
            return []

        with patch.object(ytmusic, 'ready', return_value=True), patch.object(ytmusic, '_call', side_effect=fake):
            tracks = await ytmusic.search('beleiver', 25)
        self.assertIn(('songs', False), calls)
        self.assertIn('yt:fixed', [t['id'] for t in tracks])

    async def test_one_failing_query_does_not_empty_the_results(self):
        async def fake(name, query, **kw):
            if kw.get('filter') == 'videos':
                raise RuntimeError('blocked')
            if kw.get('filter') == 'songs':
                return [item(f's{i}', 'Believer', 'Imagine Dragons') for i in range(5)]
            return []

        with patch.object(ytmusic, 'ready', return_value=True), patch.object(ytmusic, '_call', side_effect=fake):
            tracks = await ytmusic.search('believer', 25)
        self.assertEqual(len(tracks), 5)


class Pagination(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        providers._yt_ranked72.clear() if hasattr(providers._yt_ranked72, 'clear') else None

    async def test_next_page_continues_the_same_ranking(self):
        pool = [song(f'v{i}', f'Track {i}', f'Artist {i}', pos=i) for i in range(30)]
        pool.insert(5, song('orig', 'Believer', 'Imagine Dragons', pos=5, top=True))
        seen_need = []

        async def fake(query, need):
            seen_need.append(need)
            return [dict(t, _rank72=dict(t['_rank72'])) for t in pool[:need]]

        with patch.object(providers, '_youtube_candidates', side_effect=fake):
            first = await providers.search_youtube('believer pagination72', limit=10, offset=0)
            second = await providers.search_youtube('believer pagination72', limit=10, offset=10)
        self.assertEqual(first[0]['id'], 'yt:orig')
        self.assertFalse({t['id'] for t in first} & {t['id'] for t in second})
        self.assertEqual(len(second), 10)
        self.assertEqual(seen_need, [10, 20])


if __name__ == '__main__':
    unittest.main()
