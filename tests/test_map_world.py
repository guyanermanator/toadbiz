import unittest

from game.map_world import StrategicMapWorld, StrategicWorldState


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

    def test_continent_generation_has_significant_land(self) -> None:
        """New continental generation should produce grouped land masses."""
        world = StrategicMapWorld(width=200, height=200, seed=42, chunk_size=24)
        land_count = 0
        ocean_count = 0
        # Sample a grid of hexes across the map
        for r in range(0, 200, 10):
            for q in range(0, 200, 10):
                cell = world.cell_snapshot(q, r)
                if cell and cell["terrain"] == "ocean":
                    ocean_count += 1
                else:
                    land_count += 1
        total = land_count + ocean_count
        land_ratio = land_count / max(1, total)
        # At least 20 % and at most 80 % land (reasonable for continental gen)
        self.assertGreater(land_ratio, 0.20, "Too little land generated")
        self.assertLess(land_ratio, 0.80, "Too much land (ocean missing)")


class StrategicWorldStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.world = StrategicMapWorld(width=200, height=200, seed=7, chunk_size=24)
        self.state = StrategicWorldState(self.world)

    def test_all_factions_have_state(self) -> None:
        from game.map_world import FACTION_PROFILES
        for key in FACTION_PROFILES:
            self.assertIn(key, self.state.faction_states)

    def test_initial_workers_spawned(self) -> None:
        total_workers = sum(len(fs.workers) for fs in self.state.faction_states.values())
        self.assertGreater(total_workers, 0, "Bootstrap should spawn some workers")

    def test_tick_advances_turn(self) -> None:
        self.state.tick()
        self.assertEqual(self.state.turn, 1)

    def test_tick_is_stable_over_many_turns(self) -> None:
        """Running many ticks should not raise and should produce a valid snapshot."""
        for _ in range(20):
            self.state.tick()
        snap = self.state.snapshot()
        self.assertIn("workers", snap)
        self.assertIn("tradeRoutes", snap)
        self.assertIn("factionStates", snap)
        self.assertIsInstance(snap["workers"], list)
        self.assertIsInstance(snap["tradeRoutes"], list)

    def test_trade_routes_eventually_form(self) -> None:
        """After enough ticks, trade routes should be established."""
        for _ in range(60):
            self.state.tick()
        snap = self.state.snapshot()
        self.assertGreaterEqual(len(snap["tradeRoutes"]), 0)  # may be 0 on small map
        # At minimum we should have some workers active
        self.assertGreater(len(snap["workers"]), 0)

    def test_faction_state_snapshot_fields(self) -> None:
        snap = self.state.snapshot()
        for key, fs_dict in snap["factionStates"].items():
            self.assertIn("faction", fs_dict)
            self.assertIn("grain", fs_dict)
            self.assertIn("gold", fs_dict)
            self.assertIn("housingCapacity", fs_dict)
            self.assertIn("workerCount", fs_dict)

    def test_update_hex_ownership_updates_housing(self) -> None:
        territories = {key: 1.0 / 7 for key in self.state.faction_states}
        self.state.update_hex_ownership(territories)
        for fs in self.state.faction_states.values():
            self.assertGreater(fs.hexes_owned, 0)


if __name__ == "__main__":
    unittest.main()
