"""v73 search: upload titles with the artist prefix, famous songs first among
same-named ones, symbol titles, live/cover detection, per-source trust and the
match key the UI uses to fold one recording found by several sources. No network."""
import unittest

from kryonyx import search_rank72 as r72


def row(i, title, artist, kind='song', source='youtube', **f):
    out = {'id': f'{source[:2]}:{i}', 'title': title, 'artist': artist,
           'artists': [{'name': a} for a in artist.split(', ')],
           'duration': f.pop('duration', 240), 'source': source, 'views': f.pop('views', None)}
    if 'original_title' in f:
        out['original_title'] = f.pop('original_title')
    out['_rank72'] = {'kind': kind, **f}
    return out


class ArtistPrefix(unittest.TestCase):
    def test_official_video_with_artist_prefix_is_the_exact_song(self):
        rows = [row('inc', 'Бесконечность', 'Инкогнито', pos=1, plays=2_500_000),
                row('small', 'Бесконечность', 'ChensyChens', pos=2, plays=329),
                row('zv', 'Земфира — Бесконечность', 'Zemfira', kind='omv', top=True, vpos=0, plays=18_000_000,
                    original_title='Земфира — Бесконечность (Official Video)')]
        ranked = [t['id'] for t in r72.rank('бесконечность', rows)]
        self.assertEqual(ranked[0], 'yo:zv')
        self.assertEqual(r72.identity(rows[2])[0], 'бесконечность')
        self.assertIn('земфира', r72.identity(rows[2])[1])

    def test_version_tag_after_dash_is_not_an_artist(self):
        title, names = r72.identity(row('w', 'Something - Live at Wembley', 'Some Band', kind='ugc'))
        self.assertNotEqual(title, 'live at wembley')
        self.assertNotIn('something', names)


class Popularity(unittest.TestCase):
    def test_famous_song_beats_same_named_songs_higher_in_the_list(self):
        rows = [row('a', 'Believer', 'Small Artist', pos=0, plays=900),
                row('b', 'Believer', 'Imagine Dragons', pos=3, plays=2_000_000_000)]
        self.assertEqual(r72.rank('believer', rows)[0]['id'], 'yo:b')

    def test_symbol_title_trusted_when_catalogue_puts_it_first(self):
        rows = [row('inf', '∞', 'Земфира', pos=0, plays=27_000_000),
                row('x1', 'Бесконечность', 'Unknown One', pos=4, plays=30),
                row('x2', 'Бесконечность', 'Unknown Two', pos=6, plays=12)]
        ranked = [t['id'] for t in r72.rank('бесконечность', rows)]
        self.assertEqual(ranked[0], 'yo:inf')

    def test_symbol_alias_shares_catalogue_signals_with_the_readable_upload(self):
        rows = [row('inf', '∞', 'Земфира', pos=0, plays=27_000_000, duration=305),
                row('inc', 'Бесконечность', 'Инкогнито', pos=1, plays=2_500_000),
                row('zv', 'Земфира — Бесконечность', 'Zemfira', kind='omv', vpos=0, plays=18_000_000, duration=318,
                    original_title='Земфира — Бесконечность (Official Video)')]
        ranked = [t['id'] for t in r72.rank('бесконечность', rows)]
        self.assertEqual(ranked[0], 'yo:zv')
        self.assertIn('yo:inf', ranked)
        self.assertNotIn('pos', rows[2]['_rank72'])  # the caller's rows are not modified

    def test_symbol_title_deep_in_the_list_is_not_promoted(self):
        rows = [row('inf', '∞', 'Someone', pos=9, plays=100),
                row('x1', 'Бесконечность', 'Artist', pos=4, plays=3000)]
        self.assertEqual(r72.rank('бесконечность', rows)[0]['id'], 'yo:x1')


class Versions(unittest.TestCase):
    def test_concert_dates_and_venues_are_live(self):
        self.assertIn('live', r72.versions('Кино Группа крови ЦСКА арена 15.05.2021'))
        self.assertIn('live', r72.versions('КИНО - Группа крови 21.06.2026 Лужники'))
        self.assertIn('live', r72.versions('Song (Live at Glastonbury)'))
        self.assertNotIn('live', r72.versions('Группа крови'))
        self.assertNotIn('live', r72.versions('1999'))

    def test_live_upload_ranks_below_the_studio_song(self):
        rows = [row('live', 'Кино Группа крови ЦСКА арена 15.05.2021', 'Вадим Бондаренко', kind='ugc', vpos=0, plays=66_000),
                row('orig', 'Группа крови', 'Кино', pos=3, plays=1_000_000)]
        self.assertEqual(r72.rank('кино группа крови', rows)[0]['id'], 'yo:orig')

    def test_cover_channels_drop_unless_asked(self):
        rows = [row('piano', 'Believer', 'Pianella Piano', pos=1, plays=5_000_000),
                row('kids', 'Believer', 'KIDZ BOP Kids', pos=2, plays=5_000_000),
                row('aa', 'Believer', 'American Authors', pos=3, plays=5_000_000)]
        self.assertEqual(r72.rank('believer', rows)[0]['id'], 'yo:aa')
        self.assertEqual(r72.rank('believer piano', rows)[0]['id'], 'yo:piano')


class Sources(unittest.TestCase):
    def test_source_trust_orders_equal_matches(self):
        rows = [row('sc', 'Midnight Train', 'Some Artist', kind='', source='soundcloud', pos=0),
                row('sp', 'Midnight Train', 'Other Artist', kind='', source='spotify', pos=0),
                row('yt', 'Midnight Train', 'Third Artist', kind='', source='youtube', pos=0)]
        self.assertEqual([t['source'] for t in r72.rank('midnight train', rows)], ['youtube', 'spotify', 'soundcloud'])

    def test_public_match_key_and_plays(self):
        out = r72.public(row('v', 'Земфира — Бесконечность', 'Zemfira', kind='omv', plays=18_000_000,
                             original_title='Земфира — Бесконечность (Official Video)'))
        self.assertNotIn('_rank72', out)
        self.assertEqual(out['plays_n'], 18_000_000)
        self.assertEqual(out['m73'][0], 'бесконечность')
        self.assertIn('земфира', out['m73'][1])
        self.assertEqual(out['m73'][2], [])
        live = r72.public(row('l', 'Song (Live)', 'Band'))
        self.assertEqual(live['m73'][2], ['live'])


def yitem(vid, title, artist, result='song', category=None, views=None):
    out = {'videoId': vid, 'title': title, 'artists': [{'name': artist, 'id': 'UC' + vid}], 'resultType': result,
           'duration': '3:30', 'views': views}
    if category:
        out['category'] = category
    return out


class FailedCatalogueQuery(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from kryonyx import providers
        providers._yt_ranked72.clear()
        providers._search_cache.clear()

    async def test_failed_songs_query_is_retried_once(self):
        from unittest.mock import patch
        from kryonyx import ytmusic
        calls = {'songs': 0}

        async def fake(name, query, **kw):
            if kw.get('filter') == 'songs' and kw.get('ignore_spelling'):
                calls['songs'] += 1
                if calls['songs'] == 1:
                    raise RuntimeError('temporary')
                return [yitem(f's{i}', 'Believer', f'Artist {i}') for i in range(6)]
            return []

        with patch.object(ytmusic, 'ready', return_value=True), patch.object(ytmusic, '_call', side_effect=fake), \
                patch('asyncio.sleep', return_value=None):
            tracks = await ytmusic.search('believer', 25)
        self.assertEqual(calls['songs'], 2)
        self.assertEqual(len(tracks), 6)
        self.assertFalse(any(t['_rank72'].get('degraded') for t in tracks))

    async def test_still_failing_songs_mark_rows_degraded_without_caching(self):
        from unittest.mock import patch
        from kryonyx import providers, ytmusic

        async def fake(name, query, **kw):
            if kw.get('filter') == 'songs':
                raise RuntimeError('blocked')
            if kw.get('filter') == 'videos':
                return [yitem('v1', 'Believer (Cover)', 'Cover Nation', result='video')]
            return []

        with patch.object(ytmusic, 'ready', return_value=True), patch.object(ytmusic, '_call', side_effect=fake), \
                patch('asyncio.sleep', return_value=None), \
                patch.object(providers, 'ytdlp_bin') as ytdlp, patch.object(providers.youtube, 'search', return_value=[]):
            ytdlp.ready.return_value = False
            result = await providers.search('believer degraded73', sources=['youtube'], limit=20)
        self.assertTrue(result.get('degraded'))
        self.assertFalse(any('degraded73' in key for key in providers._search_cache._data))
        self.assertFalse(any('degraded73' in key for key in providers._yt_ranked72._data))


if __name__ == '__main__':
    unittest.main()
