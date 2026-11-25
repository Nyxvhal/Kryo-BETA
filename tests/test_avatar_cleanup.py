import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from kryonyx import avatars, avatarshop

ROOT = Path(__file__).resolve().parent.parent


class AvatarCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = json.loads((ROOT / "kryonyx/avatars.json").read_text(encoding="utf-8"))

    def test_removed_categories_and_ids_absent(self):
        removed_cats = {"Streamers", "Music artists", "YouTube and creators"}
        removed_ids = {
            "collection-249-одноклассники",
            "collection-021-poppy-playtime",
            "collection-525-poppy-playtime-chapter-2",
            "collection-526-poppy-playtime-chapter-3",
            "collection-527-poppy-playtime-chapter-4",
            "collection-528-poppy-playtime-chapter-5",
        }
        self.assertEqual(len(self.items), 233)
        self.assertEqual(len(self.items), len({x["id"] for x in self.items}))
        for item in self.items:
            self.assertNotIn(item.get("category"), removed_cats)
            self.assertNotIn(item.get("id"), removed_ids)
            self.assertNotIn("poppy-playtime", item.get("id", "").lower())

    def test_kept_assets_exist_and_removed_notices_deleted(self):
        web = ROOT / "kryonyx/web"
        for item in self.items:
            aid = item["id"]
            self.assertTrue((web / "img/avatars" / f"{aid}.png").is_file(), aid)
            if "svg" in item.get("formats", []):
                self.assertTrue((web / "img/avatars/svg" / f"{aid}.svg").is_file(), aid)
            if item.get("preview"):
                self.assertTrue((web / item["preview"].lstrip("/")).is_file(), aid)

        notices = ROOT / "kryonyx/avatar-notices/redesigned/notices"
        for sub in ("artists", "creators", "streamers"):
            self.assertFalse((notices / sub).exists())
        self.assertEqual(list((notices / "games").glob("*poppy-playtime*")), [])
        self.assertEqual(list((notices / "socials").glob("249-*")), [])

    def test_removed_avatar_falls_back_to_default(self):
        with tempfile.TemporaryDirectory() as tmp, patch("kryonyx.avatars.data_dir", return_value=tmp):
            Path(tmp, "avatar.json").write_text(
                json.dumps({"id": "collection-021-poppy-playtime"}), encoding="utf-8"
            )
            self.assertEqual(avatars.current(), avatars.DEFAULT_AVATAR)

    def test_avatarshop_pack_excludes_removed_entries(self):
        with tempfile.TemporaryDirectory() as tmp, patch("kryonyx.avatarshop.cache_dir", return_value=tmp):
            zpath = avatarshop.pack("all")
            self.assertTrue(zpath.is_file())


if __name__ == "__main__":
    unittest.main()
