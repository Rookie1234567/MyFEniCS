from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from mpi4py import MPI
import basix
import basix.ufl
import numpy as np

from src.adaptivity.fast_custom_element_ufl import custom_element_sha256
from src.adaptivity.fixed_trace_element_cache import (
    fixed_trace_element_build,
    load_or_build_fixed_trace_element,
)
from src.adaptivity.hcurl_regionwise_p import (
    _create_trace_interior_element_data,
    _flatten_entity_dofs,
    _selected_interpolation_operator,
)


COMM = MPI.COMM_WORLD
SOURCE_SHA = "a" * 40


def _build(trace_degree: int, interior_degree: int):
    element, audit, constructor = _create_trace_interior_element_data(
        trace_degree,
        interior_degree,
        False,
    )
    if audit["qualification_audit_executed"] is not False:
        raise AssertionError("lightweight cache fixture ran qualification")
    if constructor is None:
        raise AssertionError("cache fixture lacks custom constructor payload")
    return fixed_trace_element_build(
        element,
        build_audit=audit["construction_profile"],
        **constructor,
    )


@contextmanager
def _shared_temporary_directory():
    directory = (
        tempfile.mkdtemp(prefix="myfenics-fixed-trace-element-cache-")
        if COMM.rank == 0
        else None
    )
    resolved = Path(COMM.bcast(directory, root=0)).resolve()
    COMM.barrier()
    try:
        yield resolved
    finally:
        COMM.barrier()
        if COMM.rank == 0:
            shutil.rmtree(resolved)
        COMM.barrier()


class Task035bFixedTraceElementCacheTests(unittest.TestCase):
    def test_selected_interpolation_matches_complete_basix_operator_exactly(
        self,
    ) -> None:
        trace_element = basix.ufl.element(
            "N1curl",
            "hexahedron",
            2,
        ).basix_element
        polynomial_element = basix.ufl.element(
            "N1curl",
            "hexahedron",
            3,
        ).basix_element
        selections = (
            (
                trace_element,
                _flatten_entity_dofs(trace_element, range(3)),
            ),
            (
                polynomial_element,
                np.asarray(
                    polynomial_element.entity_dofs[3][0],
                    dtype=np.int32,
                ),
            ),
        )
        for source, selected in selections:
            with self.subTest(source_degree=source.degree):
                reference = basix.compute_interpolation_operator(
                    source,
                    polynomial_element,
                )[:, selected]
                actual = _selected_interpolation_operator(
                    source,
                    polynomial_element,
                    selected,
                )
                np.testing.assert_array_equal(actual, reference)

    def test_fast_constructor_matches_reference_element_exactly(self) -> None:
        reference, reference_audit, _ = (
            _create_trace_interior_element_data.__wrapped__(
                2,
                3,
                True,
            )
        )
        fast, fast_audit, constructor = (
            _create_trace_interior_element_data.__wrapped__(
                2,
                3,
                False,
            )
        )
        self.assertIsNotNone(constructor)
        self.assertEqual(fast.hash(), reference.hash())
        self.assertEqual(
            custom_element_sha256(fast),
            custom_element_sha256(reference),
        )
        points = np.asarray(
            ((0.17, 0.23, 0.31), (0.61, 0.47, 0.73)),
            dtype=np.float64,
        )
        np.testing.assert_array_equal(
            fast.tabulate(1, points),
            reference.tabulate(1, points),
        )
        self.assertEqual(
            reference_audit["construction_profile"]["strategy"],
            "basix_reference_full_interpolation",
        )
        profile = fast_audit["construction_profile"]
        self.assertEqual(
            profile["strategy"],
            "selected_public_interpolation_v1",
        )
        self.assertTrue(profile["polynomial_element_reused"])
        self.assertTrue(profile["selected_interpolation_enabled"])
        self.assertEqual(
            profile["stage_seconds"]["duplicate_polynomial_element"],
            0.0,
        )
        for value in profile["stage_seconds"].values():
            self.assertTrue(np.isfinite(value))
            self.assertGreaterEqual(value, 0.0)

    def test_collective_cold_write_and_warm_restore_match(self) -> None:
        with _shared_temporary_directory() as directory:
            cold, cold_audit = load_or_build_fixed_trace_element(
                trace_degree=2,
                interior_degree=3,
                cache_directory=directory,
                source_sha=SOURCE_SHA,
                cache_mode="read_write",
                comm=COMM,
                builder=_build,
            )
            self.assertEqual(
                cold_audit["status"],
                "persistent_fixed_trace_element_cache_cold_write",
            )
            self.assertTrue(cold_audit["cache_miss_on_all_ranks"])
            self.assertFalse(cold_audit["cache_hit_on_all_ranks"])
            self.assertEqual(
                cold_audit["serialization"],
                "json_plus_npz_allow_pickle_false",
            )
            cold_profile = cold_audit["cold_builder_profile"]
            self.assertEqual(
                cold_profile["schema_version"],
                "task035b.fixed-trace-element-cold-build-profile.v1",
            )
            self.assertEqual(
                cold_profile["strategy"],
                "selected_public_interpolation_v1",
            )
            self.assertEqual(
                cold_profile["aggregation"],
                "per_stage_MPI_MAX",
            )
            self.assertEqual(cold_profile["mpi_rank_count"], COMM.size)
            self.assertLessEqual(
                cold_profile["stage_seconds_max"]["total"],
                cold_audit["build_seconds_max"],
            )

            def forbidden_builder(_trace_degree: int, _interior_degree: int):
                raise AssertionError("warm restore called the element builder")

            warm, warm_audit = load_or_build_fixed_trace_element(
                trace_degree=2,
                interior_degree=3,
                cache_directory=directory,
                source_sha=SOURCE_SHA,
                cache_mode="read_only",
                comm=COMM,
                builder=forbidden_builder,
            )
            self.assertEqual(
                warm_audit["status"],
                "persistent_fixed_trace_element_cache_hit",
            )
            self.assertTrue(warm_audit["cache_hit_on_all_ranks"])
            self.assertIsNone(warm_audit["cold_builder_profile"])
            self.assertEqual(
                warm_audit["element_signature_sha256"],
                cold_audit["element_signature_sha256"],
            )
            self.assertEqual(warm.dim, cold.dim)
            self.assertEqual(warm.entity_dofs, cold.entity_dofs)
            self.assertEqual(warm.entity_closure_dofs, cold.entity_closure_dofs)
            self.assertEqual(warm.map_type, cold.map_type)

            manifests = sorted(directory.glob("fixed_trace_element_*.json"))
            payloads = sorted(directory.glob("fixed_trace_element_*.npz"))
            self.assertEqual(len(manifests), 1)
            self.assertEqual(len(payloads), 1)
            manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
            self.assertEqual(
                manifest["serialization"],
                "json_plus_npz_allow_pickle_false",
            )
            self.assertEqual(manifest["identity"]["source_sha"], SOURCE_SHA)

    def test_read_only_missing_pair_fails_closed(self) -> None:
        with _shared_temporary_directory() as directory:
            with self.assertRaises(FileNotFoundError):
                load_or_build_fixed_trace_element(
                    trace_degree=2,
                    interior_degree=3,
                    cache_directory=directory,
                    source_sha=SOURCE_SHA,
                    cache_mode="read_only",
                    comm=COMM,
                    builder=_build,
                )

    def test_corrupt_payload_fails_collectively_without_rebuild(self) -> None:
        with _shared_temporary_directory() as directory:
            load_or_build_fixed_trace_element(
                trace_degree=2,
                interior_degree=3,
                cache_directory=directory,
                source_sha=SOURCE_SHA,
                cache_mode="read_write",
                comm=COMM,
                builder=_build,
            )
            COMM.barrier()
            if COMM.rank == 0:
                payload = next(directory.glob("fixed_trace_element_*.npz"))
                with payload.open("r+b") as stream:
                    first = stream.read(1)
                    stream.seek(0)
                    stream.write(bytes((first[0] ^ 0x01,)))
            COMM.barrier()

            def forbidden_builder(_trace_degree: int, _interior_degree: int):
                raise AssertionError("corrupt cache must not rebuild silently")

            with self.assertRaises(RuntimeError):
                load_or_build_fixed_trace_element(
                    trace_degree=2,
                    interior_degree=3,
                    cache_directory=directory,
                    source_sha=SOURCE_SHA,
                    cache_mode="read_only",
                    comm=COMM,
                    builder=forbidden_builder,
                )

    def test_source_identity_and_mode_are_fail_closed(self) -> None:
        with _shared_temporary_directory() as directory:
            with self.assertRaises(ValueError):
                load_or_build_fixed_trace_element(
                    trace_degree=2,
                    interior_degree=3,
                    cache_directory=directory,
                    source_sha="short",
                    cache_mode="read_write",
                    comm=COMM,
                    builder=_build,
                )
            with self.assertRaises(ValueError):
                load_or_build_fixed_trace_element(
                    trace_degree=2,
                    interior_degree=3,
                    cache_directory=directory,
                    source_sha=SOURCE_SHA,
                    cache_mode="refresh",
                    comm=COMM,
                    builder=_build,
                )
            with self.assertRaises(ValueError):
                load_or_build_fixed_trace_element(
                    trace_degree=2,
                    interior_degree=3,
                    cache_directory=directory,
                    source_sha=SOURCE_SHA,
                    cache_mode="off",
                    comm=COMM,
                    builder=_build,
                )

    def test_rank_identity_mismatch_fails_collectively(self) -> None:
        with _shared_temporary_directory() as directory:
            rank_sha = ("a" if COMM.rank == 0 else "b") * 40
            if COMM.size == 1:
                rank_sha = SOURCE_SHA
            if COMM.size == 1:
                self.skipTest("requires at least two MPI ranks")
            with self.assertRaises(RuntimeError):
                load_or_build_fixed_trace_element(
                    trace_degree=2,
                    interior_degree=3,
                    cache_directory=directory,
                    source_sha=rank_sha,
                    cache_mode="read_write",
                    comm=COMM,
                    builder=_build,
                )

    def test_rank0_publication_failure_is_collective(self) -> None:
        with _shared_temporary_directory() as directory:
            with mock.patch(
                "src.adaptivity.fixed_trace_element_cache._publish_pair",
                side_effect=OSError("injected publication failure"),
            ):
                with self.assertRaises(RuntimeError):
                    load_or_build_fixed_trace_element(
                        trace_degree=2,
                        interior_degree=3,
                        cache_directory=directory,
                        source_sha=SOURCE_SHA,
                        cache_mode="read_write",
                        comm=COMM,
                        builder=_build,
                    )

    @unittest.skipUnless(
        os.environ.get("MYFENICS_TASK035B_P5P6_CACHE_TEST") == "1",
        "explicit high-order cache qualification only",
    )
    def test_p5_trace_p6_interior_cold_warm_exact_identity(self) -> None:
        with _shared_temporary_directory() as directory:
            cold, cold_audit = load_or_build_fixed_trace_element(
                trace_degree=5,
                interior_degree=6,
                cache_directory=directory,
                source_sha=SOURCE_SHA,
                cache_mode="read_write",
                comm=COMM,
                builder=_build,
            )

            def forbidden_builder(_trace_degree: int, _interior_degree: int):
                raise AssertionError("warm p5/p6 restore rederived the element")

            warm, warm_audit = load_or_build_fixed_trace_element(
                trace_degree=5,
                interior_degree=6,
                cache_directory=directory,
                source_sha=SOURCE_SHA,
                cache_mode="read_only",
                comm=COMM,
                builder=forbidden_builder,
            )
            points = np.asarray(
                ((0.17, 0.23, 0.31), (0.61, 0.47, 0.73)),
                dtype=np.float64,
            )
            self.assertEqual(cold.hash(), warm.hash())
            self.assertEqual(
                cold_audit["element_signature_sha256"],
                warm_audit["element_signature_sha256"],
            )
            np.testing.assert_array_equal(
                cold.tabulate(1, points),
                warm.tabulate(1, points),
            )
            self.assertEqual(warm_audit["build_seconds_max"], 0.0)


if __name__ == "__main__":
    unittest.main()
