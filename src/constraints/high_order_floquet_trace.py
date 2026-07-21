from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
from typing import Hashable, Iterable, Literal
import weakref

import basix
import numpy as np
from basix import CellType, ElementFamily, LagrangeVariant
from basix.ufl import element


PhaseKind = Literal["x", "y", "corner"]
EntityKind = Literal["edge", "face"]


@dataclass(frozen=True)
class HighOrderTraceLayout:
    """Degree-generic tensor-product N1curl trace layout."""

    degree: int
    hexahedron_dimension: int
    edge_dofs: int
    face_interior_dofs: int
    cell_interior_dofs: int
    face_trace_dofs: int
    quadrilateral_n1curl_dimension: int


@lru_cache(maxsize=4)
def high_order_trace_layout(degree: int) -> HighOrderTraceLayout:
    """Read and cross-check the p1--p4 Basix entity layout.

    Formulas are checks, not the source of the production layout.  The actual
    entity sizes come from the Basix element shipped in the qualified image.
    """

    degree = int(degree)
    if degree not in {1, 2, 3, 4}:
        raise ValueError(f"Task033 qualifies N1curl degrees 1--4, got {degree}.")
    hexa = element("N1curl", "hexahedron", degree).basix_element
    quadrilateral = element("N1curl", "quadrilateral", degree).basix_element
    edge_counts = {len(dofs) for dofs in hexa.entity_dofs[1]}
    face_counts = {len(dofs) for dofs in hexa.entity_dofs[2]}
    cell_counts = {len(dofs) for dofs in hexa.entity_dofs[3]}
    if len(edge_counts) != 1 or len(face_counts) != 1 or len(cell_counts) != 1:
        raise RuntimeError(
            "Basix returned a non-uniform hexahedron N1curl entity layout."
        )
    edge_dofs = edge_counts.pop()
    face_interior_dofs = face_counts.pop()
    cell_interior_dofs = cell_counts.pop()
    face_trace_dofs = 4 * edge_dofs + face_interior_dofs
    expected = {
        "hexahedron_dimension": 3 * degree * (degree + 1) ** 2,
        "edge_dofs": degree,
        "face_interior_dofs": 2 * degree * (degree - 1),
        "cell_interior_dofs": 3 * degree * (degree - 1) ** 2,
        "face_trace_dofs": 2 * degree * (degree + 1),
    }
    observed = {
        "hexahedron_dimension": int(hexa.dim),
        "edge_dofs": int(edge_dofs),
        "face_interior_dofs": int(face_interior_dofs),
        "cell_interior_dofs": int(cell_interior_dofs),
        "face_trace_dofs": int(face_trace_dofs),
    }
    if observed != expected:
        raise RuntimeError(
            "Basix tensor-product N1curl semantics changed; refusing to infer a high-order trace layout: "
            f"observed={observed}, expected={expected}."
        )
    if int(quadrilateral.dim) != face_trace_dofs:
        raise RuntimeError(
            "The 3D face trace and 2D N1curl degree semantics disagree: "
            f"3D trace={face_trace_dofs}, 2D dimension={quadrilateral.dim}."
        )
    return HighOrderTraceLayout(
        degree=degree,
        hexahedron_dimension=int(hexa.dim),
        edge_dofs=int(edge_dofs),
        face_interior_dofs=int(face_interior_dofs),
        cell_interior_dofs=int(cell_interior_dofs),
        face_trace_dofs=int(face_trace_dofs),
        quadrilateral_n1curl_dimension=int(quadrilateral.dim),
    )


@lru_cache(maxsize=1)
def quadrilateral_d4_vertex_permutations() -> dict[tuple[int, int, int, int], int]:
    """Return Basix's eight quadrilateral orientation permutations.

    The three face-info bits use reflection in bit 0 and a 0--3 rotation count
    in bits 1--2.  Asking Basix to permute a P1 face closure makes this mapping
    independent of a guessed vertex-numbering diagram.
    """

    p1 = basix.create_element(
        ElementFamily.P,
        CellType.hexahedron,
        1,
        LagrangeVariant.equispaced,
    )
    reference = np.asarray(p1.entity_closure_dofs[2][0], dtype=np.int32)
    if reference.shape != (4,):
        raise RuntimeError(
            f"Expected four P1 quadrilateral closure dofs, got {reference}."
        )
    mapping: dict[tuple[int, int, int, int], int] = {}
    for face_info in range(8):
        permuted = reference.copy()
        p1.permute_subentity_closure(permuted, face_info, CellType.quadrilateral)
        local_permutation = tuple(
            int(np.where(reference == value)[0][0]) for value in permuted
        )
        if local_permutation in mapping:
            raise RuntimeError(
                "Basix returned duplicate quadrilateral D4 permutations."
            )
        mapping[local_permutation] = face_info
    if len(mapping) != 8:
        raise RuntimeError(
            f"Expected eight quadrilateral D4 permutations, got {len(mapping)}."
        )
    return mapping


def quadrilateral_face_info(vertex_permutation: Iterable[int]) -> int:
    permutation = tuple(int(value) for value in vertex_permutation)
    if len(permutation) != 4 or sorted(permutation) != [0, 1, 2, 3]:
        raise ValueError(
            f"Expected a quadrilateral vertex permutation, got {permutation}."
        )
    try:
        return quadrilateral_d4_vertex_permutations()[permutation]  # type: ignore[index]
    except KeyError as exc:  # pragma: no cover - all S4 non-D4 permutations are invalid
        raise ValueError(
            f"Permutation {permutation} is not a quadrilateral D4 symmetry."
        ) from exc


@lru_cache(maxsize=4)
def _entity_transformations(degree: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high_order_trace_layout(degree)
    hexa = element("N1curl", "hexahedron", int(degree)).basix_element
    transformations = hexa.entity_transformations()
    interval = np.asarray(transformations["interval"][0], dtype=np.float64)
    quadrilateral = np.asarray(transformations["quadrilateral"], dtype=np.float64)
    if quadrilateral.shape[0] != 2:
        raise RuntimeError(
            "Basix must provide rotation and reflection generators for quadrilateral faces."
        )
    return interval, quadrilateral[0], quadrilateral[1]


def edge_coefficient_transform(
    degree: int, *, reversed_orientation: bool
) -> np.ndarray:
    """Map canonical master edge coefficients into slave coefficient ordering."""

    interval, _rotation, _reflection = _entity_transformations(int(degree))
    if not reversed_orientation:
        return np.eye(interval.shape[0], dtype=np.complex128)
    # Basix T matrices transform basis data.  Coefficients therefore use T^T.
    return np.asarray(interval.T, dtype=np.complex128)


def face_basis_transform(degree: int, face_info: int) -> np.ndarray:
    """Compose the Basix face basis transform for one D4 orientation."""

    if not 0 <= int(face_info) < 8:
        raise ValueError(f"Quadrilateral face_info must be in [0, 7], got {face_info}.")
    _interval, rotation, reflection = _entity_transformations(int(degree))
    transform = np.eye(rotation.shape[0], dtype=np.float64)
    if int(face_info) & 1:
        transform = reflection @ transform
    for _ in range((int(face_info) >> 1) & 3):
        transform = rotation @ transform
    return transform


def face_coefficient_transform(
    degree: int, vertex_permutation: Iterable[int]
) -> np.ndarray:
    """Map canonical master face-interior coefficients into slave ordering."""

    face_info = quadrilateral_face_info(vertex_permutation)
    return np.asarray(
        face_basis_transform(int(degree), face_info).T, dtype=np.complex128
    )


@dataclass(frozen=True)
class FloquetTopologyKey:
    mesh_token: Hashable
    element_family: str
    degree: int
    periodic_axes: tuple[str, ...] = ("x", "y")
    orientation_schema: str = "basix-0.10-d4-v1"


@dataclass(frozen=True)
class PhaseIndependentConstraintBlock:
    kind: PhaseKind
    slave_global_dofs: tuple[int, ...]
    master_global_dofs: tuple[int, ...]
    coefficient_transform: np.ndarray
    slave_local_dofs: tuple[int, ...] = ()
    master_owners: tuple[int, ...] = ()
    slave_owned: tuple[bool, ...] = ()
    touches_owned_cell: bool = False
    entity_kind: EntityKind = "edge"
    pair_error: float = 0.0

    def __post_init__(self) -> None:
        matrix = np.asarray(self.coefficient_transform, dtype=np.complex128)
        if matrix.shape != (len(self.slave_global_dofs), len(self.master_global_dofs)):
            raise ValueError(
                "Constraint block shape does not match slave/master dof counts: "
                f"shape={matrix.shape}, slaves={len(self.slave_global_dofs)}, "
                f"masters={len(self.master_global_dofs)}."
            )
        matrix.setflags(write=False)
        object.__setattr__(self, "coefficient_transform", matrix)
        if self.slave_local_dofs and len(self.slave_local_dofs) != len(
            self.slave_global_dofs
        ):
            raise ValueError("Local and global slave dof counts differ.")
        if self.master_owners and len(self.master_owners) != len(
            self.master_global_dofs
        ):
            raise ValueError("Master owner and global dof counts differ.")
        if self.slave_owned and len(self.slave_owned) != len(self.slave_global_dofs):
            raise ValueError("Slave ownership and global dof counts differ.")
        if self.entity_kind not in {"edge", "face"}:
            raise ValueError(f"Unsupported trace entity kind {self.entity_kind!r}.")
        if float(self.pair_error) < 0.0:
            raise ValueError("Periodic entity pairing error cannot be negative.")


@dataclass(frozen=True)
class FloquetTraceTopology:
    key: FloquetTopologyKey
    blocks: tuple[PhaseIndependentConstraintBlock, ...]
    topology_build_seconds: float
    bytes_sent: int
    bytes_received: int
    used_full_boundary_gather: bool = False
    created_dense_boundary_square: bool = False
    pair_counts: tuple[tuple[EntityKind, PhaseKind, int], ...] = ()

    def materialize(
        self,
        *,
        phase_x: complex,
        phase_y: complex,
    ) -> tuple[np.ndarray, ...]:
        phase_by_kind = {
            "x": complex(phase_x),
            "y": complex(phase_y),
            "corner": complex(phase_x) * complex(phase_y),
        }
        return tuple(
            phase_by_kind[block.kind] * block.coefficient_transform
            for block in self.blocks
        )


class FloquetTopologyCache:
    """Weak-owner-aware LRU cache whose values never contain Bloch phases.

    Production entries validate live mesh/function-space wrappers by identity.
    Weak references avoid retaining large DOLFINx graphs, and make ``id()``
    reuse in :class:`FloquetTopologyKey` fail closed.
    """

    def __init__(self, max_entries: int = 8):
        if int(max_entries) < 1:
            raise ValueError("max_entries must be positive.")
        self.max_entries = int(max_entries)
        self._values: OrderedDict[
            FloquetTopologyKey,
            tuple[
                FloquetTraceTopology,
                weakref.ReferenceType[object] | None,
                weakref.ReferenceType[object] | None,
            ],
        ] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(
        self,
        key: FloquetTopologyKey,
        *,
        mesh: object | None = None,
        space: object | None = None,
    ) -> FloquetTraceTopology | None:
        entry = self._values.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, mesh_ref, space_ref = entry
        if mesh is not None or space is not None:
            owners_match = bool(
                mesh is not None
                and space is not None
                and mesh_ref is not None
                and space_ref is not None
                and mesh_ref() is mesh
                and space_ref() is space
            )
            if not owners_match:
                self._values.pop(key, None)
                self.misses += 1
                return None
        self._values.move_to_end(key)
        self.hits += 1
        return value

    def put(
        self,
        topology: FloquetTraceTopology,
        *,
        mesh: object | None = None,
        space: object | None = None,
    ) -> None:
        if (mesh is None) != (space is None):
            raise ValueError("mesh and space cache owners must be supplied together.")
        mesh_ref = None if mesh is None else weakref.ref(mesh)
        space_ref = None if space is None else weakref.ref(space)
        self._values[topology.key] = (topology, mesh_ref, space_ref)
        self._values.move_to_end(topology.key)
        while len(self._values) > self.max_entries:
            self._values.popitem(last=False)

    def clear(self) -> None:
        self._values.clear()

    def __len__(self) -> int:
        return len(self._values)


@dataclass(frozen=True)
class DistributedPairingMetrics:
    records_sent: int
    records_received: int
    bytes_sent: int
    bytes_received: int
    pair_count: int
    used_full_boundary_gather: bool = False


def stable_pairing_rank(pair_key: Iterable[int], comm_size: int) -> int:
    """Map a periodic entity key to one deterministic pairing rank."""

    if int(comm_size) < 1:
        raise ValueError("comm_size must be positive.")
    normalized = tuple(int(value) for value in pair_key)
    digest = hashlib.blake2b(
        json.dumps(normalized, separators=(",", ":")).encode("ascii"),
        digest_size=8,
        person=b"task033",
    ).digest()
    return int.from_bytes(digest, "little", signed=False) % int(comm_size)


def _alltoallv_json_records(
    comm, buckets: list[list[dict]]
) -> tuple[list[dict], int, int]:
    """Exchange routed JSON records without replicating a whole boundary."""

    from mpi4py import MPI

    if len(buckets) != int(comm.size):
        raise ValueError(
            f"Expected {comm.size} destination buckets, got {len(buckets)}."
        )
    payloads = [
        json.dumps(bucket, separators=(",", ":"), sort_keys=True).encode("utf-8")
        for bucket in buckets
    ]
    send_counts = np.asarray([len(payload) for payload in payloads], dtype=np.int64)
    recv_counts = np.empty(int(comm.size), dtype=np.int64)
    comm.Alltoall(send_counts, recv_counts)
    send_displacements = np.zeros(int(comm.size), dtype=np.int64)
    recv_displacements = np.zeros(int(comm.size), dtype=np.int64)
    if int(comm.size) > 1:
        send_displacements[1:] = np.cumsum(send_counts[:-1])
        recv_displacements[1:] = np.cumsum(recv_counts[:-1])
    send_blob = b"".join(payloads)
    send_buffer = np.frombuffer(send_blob, dtype=np.uint8)
    recv_buffer = np.empty(int(np.sum(recv_counts)), dtype=np.uint8)
    comm.Alltoallv(
        [send_buffer, send_counts, send_displacements, MPI.BYTE],
        [recv_buffer, recv_counts, recv_displacements, MPI.BYTE],
    )
    received: list[dict] = []
    for count, displacement in zip(recv_counts, recv_displacements, strict=True):
        if int(count) == 0:
            continue
        packet = recv_buffer[int(displacement) : int(displacement + count)].tobytes()
        decoded = json.loads(packet.decode("utf-8"))
        if not isinstance(decoded, list):
            raise RuntimeError(
                "Distributed Floquet pairing received a non-list JSON packet."
            )
        received.extend(decoded)
    return received, int(np.sum(send_counts)), int(np.sum(recv_counts))


def distributed_match_periodic_records(
    comm,
    local_records: list[dict],
) -> tuple[list[dict], DistributedPairingMetrics]:
    """Match periodic slave records with masters via distributed hash routing.

    Each input record must contain JSON-compatible ``pair_key``, ``role``,
    ``global_dofs``, ``reply_rank`` and ``token`` fields.  Master records may
    be repeated by ghost contributors, but all copies must name the same global
    DOFs.  Replies are sent only to ranks that contributed a slave record.
    """

    size = int(comm.size)
    rank = int(comm.rank)
    routed: list[list[dict]] = [[] for _ in range(size)]
    for record in local_records:
        pair_key = tuple(int(value) for value in record.get("pair_key", ()))
        role = record.get("role")
        if not pair_key or role not in {"master", "slave"}:
            raise ValueError(
                f"Invalid periodic pairing record on rank {rank}: {record}."
            )
        if int(record.get("reply_rank", -1)) != rank:
            raise ValueError(
                "Each local pairing record must reply to its contributing rank."
            )
        routed[stable_pairing_rank(pair_key, size)].append(record)

    received, first_sent, first_received = _alltoallv_json_records(comm, routed)
    grouped: dict[tuple[int, ...], list[dict]] = {}
    for record in received:
        key = tuple(int(value) for value in record["pair_key"])
        grouped.setdefault(key, []).append(record)

    replies_by_rank: list[list[dict]] = [[] for _ in range(size)]
    local_errors: list[str] = []
    local_pair_count = 0
    for key, records in grouped.items():
        masters = [record for record in records if record["role"] == "master"]
        slaves = [record for record in records if record["role"] == "slave"]
        master_by_dofs: dict[tuple[int, ...], dict] = {}
        master_payload_signatures: dict[tuple[int, ...], set[str]] = {}
        for master in masters:
            master_dofs = tuple(int(value) for value in master["global_dofs"])
            comparable_payload = {
                name: master.get(name)
                for name in (
                    "pair_key",
                    "global_dofs",
                    "owners",
                    "midpoint",
                    "tangent",
                    "geometry_coords",
                    "normal_axis",
                )
                if name in master
            }
            master_payload_signatures.setdefault(master_dofs, set()).add(
                json.dumps(
                    comparable_payload,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
            current = master_by_dofs.get(master_dofs)
            if current is None or (
                bool(master.get("owns_any", False)),
                -int(master["reply_rank"]),
            ) > (
                bool(current.get("owns_any", False)),
                -int(current["reply_rank"]),
            ):
                master_by_dofs[master_dofs] = master
        inconsistent_master_payloads = [
            dofs
            for dofs, signatures in master_payload_signatures.items()
            if len(signatures) != 1
        ]
        if inconsistent_master_payloads:
            local_errors.append(
                f"key={key}: inconsistent_master_payloads={inconsistent_master_payloads}"
            )
            continue
        if len(master_by_dofs) != 1 or not slaves:
            local_errors.append(
                f"key={key}: unique_masters={len(master_by_dofs)}, slave_records={len(slaves)}"
            )
            continue
        master = next(iter(master_by_dofs.values()))
        slave_entities = {
            tuple(int(value) for value in slave["global_dofs"]) for slave in slaves
        }
        if len(slave_entities) != 1:
            local_errors.append(
                f"key={key}: distinct_slave_entities={len(slave_entities)}"
            )
            continue
        local_pair_count += 1
        master_payload = {
            name: value
            for name, value in master.items()
            if name not in {"role", "reply_rank", "token"}
        }
        for slave in slaves:
            replies_by_rank[int(slave["reply_rank"])].append(
                {
                    "token": slave["token"],
                    "pair_key": list(key),
                    "master": master_payload,
                }
            )

    error_count = int(comm.allreduce(len(local_errors)))
    if error_count:
        detail = (
            local_errors[0]
            if local_errors
            else "error was detected on another pairing rank"
        )
        raise RuntimeError(
            "Distributed periodic entity pairing is not one-to-one: "
            f"global_error_count={error_count}; {detail}."
        )

    replies, second_sent, second_received = _alltoallv_json_records(
        comm, replies_by_rank
    )
    global_pairs = int(comm.allreduce(local_pair_count))
    metrics = DistributedPairingMetrics(
        records_sent=len(local_records),
        records_received=len(replies),
        bytes_sent=first_sent + second_sent,
        bytes_received=first_received + second_received,
        pair_count=global_pairs,
    )
    return replies, metrics
