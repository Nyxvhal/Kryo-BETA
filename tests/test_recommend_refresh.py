import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from aiohttp.test_utils import AioHTTPTestCase

from kryonyx import recommend, server


class RecommendRefreshTests(AioHTTPTestCase):
    async def get_application(self):
        return server.build_app()

    def setUp(self):
        super().setUp()
        self._tmp = tempfile.TemporaryDirectory()
        self._patch_cache = patch("kryonyx.recommend.cache_dir", return_value=self._tmp.name)
        self._patch_cache.start()
        recommend._cache.clear()
        recommend._disk_invalidated = False

    def tearDown(self):
        self._patch_cache.stop()
        self._tmp.cleanup()
        super().tearDown()

    async def test_fresh_refresh_invalidates_disk_cache_and_returns_new_generation(self):
        first_rows = [{"id": "mix1", "title": "Mix 1", "kind": "tracks", "items": [{"id": f"yt:a{i}", "title": f"A{i}"} for i in range(6)]}]
        second_rows = [{"id": "mix2", "title": "Mix 2", "kind": "tracks", "items": [{"id": f"yt:b{i}", "title": f"B{i}"} for i in range(6)]}]
        recommend._save_rows(first_rows)

        async def fake_build(limit_rows=12, exclude_ids=None):
            recommend._cache[f"rows:{limit_rows}"] = (9999999999.0, second_rows)
            recommend._cache["rows"] = (9999999999.0, second_rows)
            recommend._save_rows(second_rows)
            return second_rows

        with patch("kryonyx.recommend.build_rows", side_effect=fake_build) as mock_build, \
             patch("kryonyx.extras.fill_thumbnails", new=AsyncMock()):
            resp1 = await self.client.request("GET", "/api/recommend?rows=12")
            self.assertEqual(resp1.status, 200)
            data1 = await resp1.json()
            self.assertEqual(data1["rows"][0]["id"], "mix1")
            self.assertTrue(data1["cached"])

            resp2 = await self.client.request("GET", "/api/recommend?rows=12&fresh=1&exclude=yt:a0,yt:a1")
            self.assertEqual(resp2.status, 200)
            data2 = await resp2.json()
            self.assertEqual(mock_build.call_count, 1)
            self.assertEqual(data2["rows"][0]["id"], "mix2")
            self.assertFalse(data2["cached"])
            self.assertGreater(data2["generation"], data1["generation"])


if __name__ == "__main__":
    unittest.main()
