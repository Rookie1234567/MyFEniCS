"""Task-local optimizer transactions; never modify PyTorch or roll back costs."""

import hashlib
from copy import deepcopy


def parameter_hash(parameters):
    digest = hashlib.sha256()
    for value in parameters:
        digest.update(value.detach().cpu().numpy().tobytes())
    return digest.hexdigest()


class OptimizerTransaction:
    """The only accepted boundary is a normally completed outer step.

    PyTorch may move live parameters before invoking a line-search closure.
    Restore parameters, gradients and optimizer state together on exceptions.
    Billing counters belong to the caller and are deliberately not restored.
    """

    def __init__(self, parameters):
        self.parameters = tuple(parameters)
        self.committed = None
        self.last_trial = None
        self.attempts = 0
        self.completed = 0
        self.interrupted = False

    def _capture(self, optimizer, phase, counts, state_kind):
        return dict(
            parameters=[p.detach().clone() for p in self.parameters],
            gradients=[
                None if p.grad is None else p.grad.detach().clone()
                for p in self.parameters
            ],
            parameter_sha256=parameter_hash(self.parameters),
            optimizer=deepcopy(optimizer.state_dict()),
            optimizer_class=type(optimizer).__name__,
            phase=phase,
            state_kind=state_kind,
            completed_outer_id=self.completed,
            counts_at_boundary=deepcopy(counts()),
            acceptance="NORMAL_OUTER_RETURN" if self.completed else "INITIAL_BOUNDARY",
            internal_wolfe_acceptance="UNKNOWN_NOT_OBSERVED",
            checkpoint_qualification="PARAMETERS_AND_OPTIMIZER_STATE_CONSISTENT",
        )

    def restore(self, optimizer, snapshot):
        import torch

        with torch.no_grad():
            for parameter, value, gradient in zip(
                self.parameters,
                snapshot["parameters"],
                snapshot["gradients"],
                strict=True,
            ):
                parameter.copy_(value)
                parameter.grad = None if gradient is None else gradient.clone()
        optimizer.load_state_dict(deepcopy(snapshot["optimizer"]))
        if parameter_hash(self.parameters) != snapshot["parameter_sha256"]:
            raise RuntimeError("transaction restore parameter identity failure")

    def step(self, optimizer, operation, *, phase, counts):
        self.attempts += 1
        boundary = self._capture(
            optimizer,
            phase,
            counts,
            "LAST_COMPLETED_OUTER_STEP"
            if self.completed
            else "INITIAL_COMMITTED_STATE",
        )
        self.committed = boundary
        try:
            result = operation()
        except BaseException as error:
            self.last_trial = dict(
                parameters=[p.detach().clone() for p in self.parameters],
                parameter_sha256=parameter_hash(self.parameters),
                state_kind="LAST_TRIAL_AT_EXCEPTION",
                phase=phase,
                outer_attempt_id=self.attempts,
                closure_id=counts().get("closures"),
                counts_at_exception=deepcopy(counts()),
                exception=type(error).__name__,
                acceptance="UNKNOWN_NOT_COMMITTED",
                checkpoint_qualification="PARAMETER_ONLY_CHECKPOINT_NOT_RESUMABLE",
            )
            self.restore(optimizer, boundary)
            self.interrupted = True
            raise
        self.completed += 1
        self.committed = self._capture(
            optimizer, phase, counts, "LAST_COMPLETED_OUTER_STEP"
        )
        return result

    def save(self, directory):
        from pathlib import Path

        import torch

        directory = Path(directory)
        records = {}
        for name, value in (
            ("committed", self.committed),
            ("last_trial", self.last_trial),
        ):
            if value is None:
                records[name] = None
                continue
            path = directory / (name + "_optimizer_snapshot.pt")
            torch.save(value, path)
            records[name] = {
                key: item
                for key, item in value.items()
                if key not in ("parameters", "gradients", "optimizer")
            }
            records[name].update(
                path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )
        records.update(
            attempts=self.attempts,
            completed=self.completed,
            interrupted=self.interrupted,
            consumed_counters_rolled_back=False,
            installed_pytorch_modified=False,
        )
        return records
