"""Opt-in complex rank-eight tensor train fields; no FE or reference imports."""

import numpy as np
import torch
from time import perf_counter


class Sin(torch.nn.Module):
    def forward(self, x):
        return torch.sin(x)


class FTTField(torch.nn.Module):
    def __init__(self, bounds, model_kind, seed=4213701):
        super().__init__()
        if model_kind not in ("fttnn", "chebtt"):
            raise ValueError("UNKNOWN_FTT_MODEL_KIND")
        self.model_kind = model_kind
        self.costs = dict(core_evaluation=0.0, contraction=0.0)
        torch.manual_seed(seed)
        box = torch.as_tensor(bounds, dtype=torch.float64)
        self.register_buffer("center", box.mean(1))
        self.register_buffer("half_width", (box[:, 1] - box[:, 0]) / 2)
        self.register_buffer(
            "initial_core_scales", torch.ones(2, 3, dtype=torch.float64)
        )
        self.shapes = ((3, 1, 8, 2), (3, 8, 8, 2), (3, 8, 1, 2))
        if model_kind == "fttnn":
            self.cores = torch.nn.ModuleList()
            for shape in self.shapes:
                core = torch.nn.Sequential(
                    torch.nn.Linear(1, 16, dtype=torch.float64),
                    Sin(),
                    torch.nn.Linear(16, 16, dtype=torch.float64),
                    Sin(),
                    torch.nn.Linear(16, int(np.prod(shape)), dtype=torch.float64),
                )
                for layer in core:
                    if isinstance(layer, torch.nn.Linear):
                        torch.nn.init.xavier_uniform_(layer.weight)
                        torch.nn.init.zeros_(layer.bias)
                self.cores.append(core)
            torch.nn.init.zeros_(self.cores[2][-1].weight)
            torch.nn.init.zeros_(self.cores[2][-1].bias)
        else:
            self.cores = torch.nn.ParameterList(
                [
                    torch.nn.Parameter(
                        torch.randn(19, *s, dtype=torch.float64) / np.sqrt(38)
                    )
                    for s in self.shapes
                ]
            )
            with torch.no_grad():
                self.cores[2].zero_()
        expected = 9072 if model_kind == "fttnn" else 9120
        if sum(p.numel() for p in self.parameters()) != expected:
            raise ValueError("FTT_PARAMETER_INVENTORY")
        # Optional normalization is deliberately NOT used: this is the exact
        # frozen Xavier/normal initialization, with no adaptive gauge change.

    def core(self, axis, normalized):
        if self.model_kind == "fttnn":
            real = self.cores[axis](normalized.reshape(-1, 1)).reshape(
                -1, *self.shapes[axis]
            )
        else:
            x = normalized.reshape(-1)
            terms = [torch.ones_like(x), x]
            for _ in range(2, 19):
                terms.append(2 * x * terms[-1] - terms[-2])
            real = torch.einsum(
                "nt,t...->n...", torch.stack(terms, 1), self.cores[axis]
            )
        return torch.complex(real[..., 0], real[..., 1])

    def forward(self, coordinates):
        x = (coordinates - self.center) / self.half_width
        started = perf_counter()
        cores = [self.core(i, x[:, i]) for i in range(3)]
        self.costs["core_evaluation"] += perf_counter() - started
        started = perf_counter()
        value = torch.einsum("nsij,nsjk,nskl->nsil", *cores)[:, :, 0, 0]
        self.costs["contraction"] += perf_counter() - started
        return value

    def nonzero_qualification_state(self, seed=4213802):
        generator = torch.Generator().manual_seed(seed)
        with torch.no_grad():
            if self.model_kind == "fttnn":
                layer = self.cores[2][-1]
                layer.weight.copy_(
                    0.03
                    * torch.randn(
                        layer.weight.shape, generator=generator, dtype=torch.float64
                    )
                )
                layer.bias.copy_(
                    0.01
                    * torch.randn(
                        layer.bias.shape, generator=generator, dtype=torch.float64
                    )
                )
            else:
                self.cores[2].copy_(
                    0.03
                    * torch.randn(
                        self.cores[2].shape, generator=generator, dtype=torch.float64
                    )
                )
