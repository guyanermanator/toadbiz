import unittest

from game.map_world import StrategicMapWorld


class StrategicMapWorldTests(unittest.TestCase):
    def test_generation_is_deterministic(self) -> None:
        world_a = StrategicMapWorld(width=1000, height=1000, seed=2026, chunk_size=24)
        world_b = StrategicMapWorld(width=1000, height=1000, seed=2026, chunk_size=24)
        self.assertEqual(world_a.cell_snapshot(321, 654), world_b.cell_snapshot(321, 654))

    def test_faction_starts_are_unique_and_on_land(self) -> None:
        world = StrategicMapWorld(width=1000, height=1000, seed=77, chunk_size=24)
        starts = list(world.faction_starts.values())
        self.assertEqual(len(starts), len(set((s.q, s.r) for s in starts)))
        for start in starts:
            cell = world.cell_snapshot(start.q, start.r)
            self.assertIsNotNone(cell)
            self.assertNotEqual(cell["terrain"], "ocean")

    def test_chunk_contains_multi_resource_tiles(self) -> None:
        world = StrategicMapWorld(width=1000, height=1000, seed=5, chunk_size=24)
        multi_resource_tiles = 0
        for chunk_q in range(3):
            for chunk_r in range(3):
                chunk = world.chunk_snapshot(chunk_q, chunk_r)
                multi_resource_tiles += sum(1 for cell in chunk["cells"] if len(cell.get("resources", [])) > 1)
        self.assertGreater(multi_resource_tiles, 0)

    def test_metadata_reports_expected_shape(self) -> None:
        world = StrategicMapWorld(width=1000, height=1000, seed=1, chunk_size=24)
        meta = world.metadata_snapshot()
        self.assertEqual(meta["width"], 1000)
        self.assertEqual(meta["height"], 1000)
        self.assertEqual(meta["chunkSize"], 24)
        self.assertIn("toad", meta["factions"])


if __name__ == "__main__":
    unittest.main()
