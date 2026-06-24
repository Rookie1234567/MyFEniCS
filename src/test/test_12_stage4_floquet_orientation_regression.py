from __future__ import annotations

import inspect
import unittest

from src.constraints import floquet_3d


class Stage4FloquetOrientationRegressionTests(unittest.TestCase):
    def test_topological_edge_context_uses_dolfinx_entity_permutations(self):
        source = inspect.getsource(floquet_3d._build_topological_edge_context)

        self.assertIn("create_entity_permutations", source)
        self.assertIn("entities_to_geometry", source)
        self.assertRegex(source, r"entities_to_geometry\([^\\n]+True\)")


if __name__ == "__main__":
    unittest.main()
