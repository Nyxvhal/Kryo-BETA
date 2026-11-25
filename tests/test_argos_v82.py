"""Offline API contract; set KRYO_TEST_ARGOS=1 for a locally prepared en→ru model."""
import os
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch
from kryonyx import lyric_translate as tr, server
from aiohttp.test_utils import TestClient, TestServer

class ArgosValidation(unittest.IsolatedAsyncioTestCase):
    async def test_bad_input_and_languages(self):
        for lines, target, source in [([], 'ru','en'),(['x']*241,'ru','en'),(['x\ny'],'ru','en'),([' '],'ru','en'),(['hi'],'ru',[]),(['hi'],'en','en')]:
            with self.subTest(source=source, target=target), self.assertRaises(ValueError):
                await tr.translate_offline(lines,target,source)

    async def test_busy(self):
        async with tr._offline_slots:
            with self.assertRaises(tr.TranslationUnavailable) as exc:
                await tr.translate_offline(['hi'],'ru','en')
        self.assertEqual(exc.exception.code,'busy')

    @unittest.skipUnless(os.getenv('KRYO_TEST_ARGOS') == '1', 'prepare Argos en→ru model to run integration test')
    async def test_real_offline_translation(self):
        lines=['Hello world.','','I love music.','Hello world.']
        data=await tr.translate_offline(lines,'ru','en')
        self.assertEqual(data['provider'],'argos-offline-v1')
        self.assertEqual(data['fingerprint'],tr.fingerprint(lines))
        self.assertEqual([r['original'] for r in data['results']], lines)
        self.assertEqual([r['status'] for r in data['results']],['ok','empty','ok','ok'])
        self.assertIn('мир',data['translations'][0].lower())
        self.assertEqual(data['translations'][0],data['translations'][3])
    @unittest.skipUnless(os.getenv('KRYO_TEST_ARGOS') == '1', 'prepare Argos and langdetect')
    async def test_auto_detection_and_short_text(self):
        lines=['The night is quiet and the stars are shining bright above us', 'I hear the music and I want to sing with you forever']
        result=await tr.translate_offline(lines,'ru','auto',lines)
        self.assertEqual(result['source'],'en');self.assertEqual(result['state'],'complete')
        with self.assertRaises(tr.TranslationUnavailable) as error:
            await tr.translate_offline(['Hi'],'ru','auto',['Hi'])
        self.assertEqual(error.exception.code,'language')

class PartialResults(unittest.IsolatedAsyncioTestCase):
    async def test_good_rows_survive_a_failed_line(self):
        tr._memory_cache.clear()
        with patch.object(tr, '_load_disk_cache', return_value={}), patch.object(tr, '_save_disk_cache'):
            async def fake_translate_unique(session, sem, text, source, target):
                if text == 'bad':
                    return '', None, 'line_failed'
                return 'хорошо', 'en', None

            with patch.object(tr, '_translate_unique_line', side_effect=fake_translate_unique):
                data = await tr.translate_offline(['ok', 'bad', ''], 'ru', 'en')
        self.assertEqual(data['provider'], 'kryo-translate-v2')
        self.assertEqual(data['state'], 'partial')
        self.assertEqual(data['translations'], ['хорошо', '', ''])

    async def test_live_online_translation_when_network_available(self):
        tr._memory_cache.clear()
        lines = ['Hello world', '', 'Music is life', 'Hello world']
        try:
            data = await tr.translate_offline(lines, 'ru', 'auto')
        except tr.TranslationUnavailable as exc:
            self.skipTest(f'Online translation unavailable in test env: {exc}')
        self.assertEqual(data['provider'], 'kryo-translate-v2')
        self.assertEqual(data['state'], 'complete')
        self.assertEqual(data['fingerprint'], tr.fingerprint(lines))
        self.assertEqual([r['original'] for r in data['results']], lines)
        self.assertEqual([r['status'] for r in data['results']], ['ok', 'empty', 'ok', 'ok'])
        self.assertEqual(data['translations'][0], data['translations'][3])
        self.assertTrue(any('а' <= ch.lower() <= 'я' or ch.lower() == 'ё' for ch in data['translations'][0]))

class Api(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        app=server.build_app();app.on_startup.clear();self.client=TestClient(TestServer(app));await self.client.start_server()
    async def asyncTearDown(self): await self.client.close()
    async def test_cancel_stops_active_task_and_releases_slot(self):
        started, stopped = asyncio.Event(), asyncio.Event()
        async def fake(*args):
            try:
                started.set();await asyncio.sleep(60)
            finally: stopped.set()
        rid='a'*32
        with patch.object(tr,'translate_offline',side_effect=fake):
            request=asyncio.create_task(self.client.post('/api/lyrics/translate',json={'lines':['x'],'source':'en','target':'ru','request_id':rid}))
            await asyncio.wait_for(started.wait(),2)
            response=await self.client.post('/api/lyrics/translate/cancel',json={'request_id':rid})
            self.assertEqual(response.status,200);self.assertTrue(stopped.is_set())
            response=await request;self.assertEqual(response.status,499)
        self.assertNotIn(rid,self.client.server.app['translation_jobs'])

    async def test_cancel_arriving_first_is_honored(self):
        rid='b'*32
        response=await self.client.post('/api/lyrics/translate/cancel',json={'request_id':rid});self.assertEqual(response.status,200)
        with patch.object(tr,'translate_offline',AsyncMock()) as fn:
            response=await self.client.post('/api/lyrics/translate',json={'lines':['x'],'source':'en','target':'ru','request_id':rid})
            self.assertEqual(response.status,499);fn.assert_not_awaited()

    async def test_contract_and_origin(self):
        with patch.object(tr,'translate_offline',AsyncMock(return_value={'provider':'argos-offline-v1'})) as fn:
            response=await self.client.post('/api/lyrics/translate',json={'lines':['Hello'],'source':'en','target':'ru'})
            self.assertEqual(response.status,200);self.assertEqual((await response.json())['provider'],'argos-offline-v1')
            fn.assert_awaited_once_with(['Hello'],'ru','en',None)
        response=await self.client.post('/api/lyrics/translate',json={'lines':['x'],'target':'ru','source':'en'},headers={'Origin':'https://evil.invalid'})
        self.assertEqual(response.status,403)
