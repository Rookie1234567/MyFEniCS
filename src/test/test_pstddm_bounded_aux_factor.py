from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from src.solvers.pstddm_bounded_aux_factor import (
    ExactBoundedAuxiliaryFactor,
    _RuntimePorts,
    csr_conversion_admission,
)


def _observation(*, cap=8 * 2**30, live=2 * 2**30,
                 available=8 * 2**30, margin=512 * 2**20):
    return {
        "effective_cap_bytes": cap,
        "live_tree_and_supervisor_bytes": live,
        "margin_bytes": margin,
        "system": {"available": available},
    }


def test_conversion_admission_uses_exact_csr_nnz_and_separate_mumps_gate():
    result = csr_conversion_admission(
        1234,
        _observation(),
        available_floor_bytes=2 * 2**30,
        future_co_resident_reserve_bytes=3 * 2**30,
    )
    assert result["matrix_stored_nnz"] == 1234
    assert result["petsc_conversion_upper_bytes"] == 24 * 1234
    assert result["conversion_charge_bytes"] == 24 * 1234 + 256 * 2**20 + 3 * 2**30
    assert result["passed"] is True
    assert result["MUMPS_workspace_not_included"] is True


def test_conversion_admission_stops_when_available_floor_leaves_no_headroom():
    result = csr_conversion_admission(
        10,
        _observation(cap=2 * 2**30, live=0, available=2 * 2**30, margin=512 * 2**20),
        available_floor_bytes=2 * 2**30,
    )
    assert result["passed"] is False


class _FakeVec:
    def __init__(self, size):
        self.values = np.zeros(size, dtype=np.complex128)
        self.destroyed = False

    def getSize(self):
        return len(self.values)

    def setArray(self, values):
        self.values[:] = values

    def norm(self):
        return float(np.linalg.norm(self.values))

    def axpy(self, alpha, other):
        self.values[:] += alpha * other.values

    def getArray(self, readonly=False):
        return self.values

    def destroy(self):
        self.destroyed = True


class _FakeComm:
    def getSize(self):
        return 1


class _FakeMat:
    def __init__(self, dense):
        self.dense = dense
        self.destroyed = False

    def getInfo(self):
        return {"nz_used": int(np.count_nonzero(self.dense))}

    def getSize(self):
        return self.dense.shape

    def getComm(self):
        return _FakeComm()

    def createVecRight(self):
        return _FakeVec(self.dense.shape[1])

    def createVecLeft(self):
        return _FakeVec(self.dense.shape[0])

    def mult(self, x, y):
        y.values[:] = self.dense @ x.values

    def destroy(self):
        self.destroyed = True


class _FakeFactor:
    def __init__(self, matrix, controls, lifecycle):
        self.matrix = matrix
        self.factor = self
        self.controls = {str(key): int(value) for key, value in controls.items()}
        self.lifecycle = lifecycle
        self.closed = False
        self.lifecycle.append(("create_factor", self.controls.copy()))

    def symbolic(self):
        self.lifecycle.append(("symbolic", self.controls.copy()))
        return {"1": 0, "2": 0, "3": 1, "4": 2, "16": 128, "17": 32,
                "26": 0, "27": 0}

    def numeric(self):
        self.lifecycle.append(("numeric", self.controls.copy()))

    def solve(self, b, x):
        x.values[:] = np.linalg.solve(self.matrix.dense, b.values)
        self.lifecycle.append(("solve", self.controls.copy()))

    def getMumpsInfog(self, index):
        return {1: 0, 2: 0, 3: 1, 4: 2, 9: 3, 16: 128, 17: 32,
                19: 32, 22: 32, 26: 0, 27: 0}[index]

    def close(self):
        self.closed = True
        self.lifecycle.append(("close_factor", self.controls.copy()))


def test_explicit_owner_admits_before_conversion_freezes_icntl23_and_closes(tmp_path: Path):
    lifecycle = []
    created = {}

    def matrix_from_csr(csr, *, comm=None):
        lifecycle.append(("convert", int(csr.nnz)))
        created["matrix"] = _FakeMat(csr.toarray())
        return created["matrix"]

    def factor_factory(matrix, api, *, controls):
        factor = _FakeFactor(matrix, controls, lifecycle)
        created.setdefault("factors", []).append(factor)
        return factor

    def observe(stage):
        lifecycle.append(("observe", stage))
        return _observation()

    def admit(stage, byte_count, *, estimate_basis):
        lifecycle.append(("admit", stage, int(byte_count)))

    runtime = _RuntimePorts(
        matrix_from_csr=matrix_from_csr,
        index_dtype=lambda: np.dtype(np.int32),
        load_shim=lambda directory, **kwargs: (object(), {"shim_sha256": "test"}),
        factor_factory=factor_factory,
        budget_function=lambda info, nnz, observation, **kwargs: {
            "passed": True,
            "matrix_stored_nnz": int(nnz),
            "numeric_ICNTL23_MB": 128,
            "future_numeric_bytes": 1 * 2**30,
        },
        compiler_command=lambda: ["test-compiler"],
    )
    matrix = sparse.eye(3, dtype=np.complex128, format="csr")
    owner = ExactBoundedAuxiliaryFactor(
        matrix,
        observe=observe,
        admit=admit,
        directory=tmp_path,
        available_floor_bytes=2 * 2**30,
        runtime=runtime,
    )

    first_conversion = next(i for i, item in enumerate(lifecycle) if item[0] == "convert")
    conversion_admit = next(i for i, item in enumerate(lifecycle)
                            if item[:2] == ("admit", "auxiliary_petsc_csr_conversion"))
    assert conversion_admit < first_conversion
    assert owner.audit["numeric_owner_controls"]["23"] == 128
    assert owner.audit["probe_relative_residual"] <= 1e-9
    assert owner.audit["numeric_owner_factor_inventory"]["mumps_raw_infog"]["16"] == 128
    assert owner.audit["numeric_owner_factor_inventory"]["factor_nnz_corrected"] == 3
    solution = owner.solve(np.asarray([1.0 + 2j, 3.0, -4j]))
    residual = owner.audit["last_solve_relative_residual"]
    assert np.allclose(solution, [1.0 + 2j, 3.0, -4j])
    assert residual == 0.0
    owner.close()
    assert created["matrix"].destroyed is True
    assert all(factor.closed for factor in created["factors"])
    assert owner.audit["cleanup_status"] == "closed"
    assert (tmp_path / "auxiliary_factor_audit.json").is_file()


def test_conversion_gate_rejection_happens_before_petsc_and_factor_creation(tmp_path: Path):
    lifecycle = []
    runtime = _RuntimePorts(
        matrix_from_csr=lambda *args, **kwargs: pytest.fail("conversion must not start"),
        index_dtype=lambda: np.dtype(np.int32),
        load_shim=lambda *args, **kwargs: pytest.fail("factor setup must not start"),
        factor_factory=lambda *args, **kwargs: pytest.fail("factor setup must not start"),
        budget_function=lambda *args, **kwargs: pytest.fail("factor setup must not start"),
        compiler_command=lambda: None,
    )
    with pytest.raises(MemoryError, match="AUX_CSR_PETSC_CONVERSION_RESOURCE_GATE"):
        ExactBoundedAuxiliaryFactor(
            sparse.eye(2, dtype=np.complex128, format="csr"),
            observe=lambda stage: _observation(
                cap=2 * 2**30, live=0, available=2 * 2**30, margin=512 * 2**20,
            ),
            admit=lambda *args, **kwargs: lifecycle.append(args),
            directory=tmp_path,
            available_floor_bytes=2 * 2**30,
            runtime=runtime,
        )
    assert lifecycle == []
