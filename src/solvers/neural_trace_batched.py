"""Same full Nedelec moments, one graph per eight owner cells.

Cache geometry and phase only; retain every q15 interpolation point and moment.
The original owner/orientation/MPC coordinates and parameter order are unchanged.
"""

from time import perf_counter

import numpy as np
import torch


class BatchedMoments:
    def __init__(self, model, packet, batch_size=8, cache_limit=512 * 2**20):
        if batch_size != 8:
            raise ValueError("only the reviewed batch8 candidate")
        began = perf_counter()
        self.batch_size = batch_size
        self.active_rows = int(packet["active_rows"])
        self.cells = np.flatnonzero(np.any(packet["owner_rows"] >= 0, axis=1))
        count = len(self.cells)
        points = len(packet["reference_points"])
        # All stored FP64 coordinates/phases, J, orientation, interpolation,
        # and owner indices; allocation is checked BEFORE constructing them.
        self.cache_upper_bytes = count * points * (3 * 8 + 8 * 16)
        self.cache_upper_bytes += (
            packet["transforms"].size * 16 + packet["interpolation"].size * 16
        )
        self.cache_upper_bytes += count * (9 * 16 + packet["owner_rows"].shape[1] * 24)
        if self.cache_upper_bytes > cache_limit:
            raise ValueError("new persistent batch cache exceeds reviewed 512MiB")
        self.interpolation = torch.as_tensor(
            packet["interpolation"], dtype=torch.complex128
        )
        self.transforms = torch.as_tensor(packet["transforms"], dtype=torch.complex128)
        reference = torch.as_tensor(packet["reference_points"], dtype=torch.float64)
        normalized, phases = [], []
        self.owners = []
        for cell in self.cells:
            jacobian = torch.as_tensor(packet["jacobians"][cell], dtype=torch.float64)
            origin = torch.as_tensor(packet["origins"][cell], dtype=torch.float64)
            coordinates = origin + reference @ jacobian.T
            normalized.append((coordinates - model.center) / model.half_width)
            phases.append(torch.exp(1j * (coordinates @ model.wavevectors.T)))
            rows = packet["owner_rows"][cell]
            selected = np.flatnonzero(rows >= 0)
            self.owners.append((rows[selected].copy(), torch.as_tensor(selected)))
        self.normalized = torch.stack(normalized)
        self.phases = torch.stack(phases)
        self.jacobians = torch.as_tensor(
            packet["jacobians"][self.cells], dtype=torch.complex128
        )
        self.orientation = torch.as_tensor(packet["orientation_ids"][self.cells])
        tensors = [
            self.interpolation,
            self.transforms,
            self.normalized,
            self.phases,
            self.jacobians,
            self.orientation,
        ]
        self.cache_bytes = sum(t.numel() * t.element_size() for t in tensors)
        self.cache_bytes += sum(
            rows.nbytes + selected.numel() * selected.element_size()
            for rows, selected in self.owners
        )
        self.cache_bytes += self.cells.nbytes
        if self.cache_bytes > cache_limit:
            raise ValueError("actual persistent cache exceeds declared limit")
        self.setup_seconds = perf_counter() - began

    def blocks(self, model):
        points = self.normalized.shape[1]
        for start in range(0, len(self.cells), self.batch_size):
            stop = min(start + self.batch_size, len(self.cells))
            width = stop - start
            envelopes = model.envelopes(
                self.normalized[start:stop].reshape(-1, 3)
            ).reshape(width, points, 8, 3, 2)
            complex_envelopes = torch.complex(envelopes[..., 0], envelopes[..., 1])
            physical = torch.sum(
                complex_envelopes * self.phases[start:stop, :, :, None], dim=2
            )
            pulled = torch.bmm(physical, self.jacobians[start:stop])
            moments = pulled.transpose(1, 2).reshape(width, -1) @ self.interpolation.T
            oriented = torch.bmm(
                self.transforms[self.orientation[start:stop]], moments[:, :, None]
            )[:, :, 0]
            rows = np.concatenate([item[0] for item in self.owners[start:stop]])
            values = torch.cat(
                [
                    oriented[i, indices]
                    for i, (_, indices) in enumerate(self.owners[start:stop])
                ]
            )
            yield rows, values

    def forward(self, model):
        result = np.empty(self.active_rows, dtype=np.complex128)
        with torch.no_grad():
            for rows, values in self.blocks(model):
                result[rows] = values.numpy()
        return result

    def vjp(self, model, dual):
        model.zero_grad(set_to_none=True)
        for rows, values in self.blocks(model):
            torch.real(torch.vdot(torch.as_tensor(dual[rows]), values)).backward()
        return (
            torch.cat([p.grad.reshape(-1) for p in model.parameters()])
            .detach()
            .numpy()
            .copy()
        )

    def identity(self):
        return dict(
            batch_size=self.batch_size,
            owner_cells=len(self.cells),
            all_points_retained=True,
            points_per_cell=self.normalized.shape[1],
            full_local_moments=self.interpolation.shape[0],
            cache_upper_bytes=self.cache_upper_bytes,
            new_persistent_cache_bytes=self.cache_bytes,
            cache_limit_bytes=512 * 2**20,
            setup_seconds=self.setup_seconds,
            original_orientation_and_owner=True,
            MPC_mapping="unchanged canonical masters; original action expands complex slave phases",
            no_autograd_graph_retained_between_batches=True,
        )
