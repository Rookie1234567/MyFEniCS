"""CPU-only surrogate modelling utilities for Task003.

The package deliberately keeps the FEM runner and its virtual environment out
of the training path.  It consumes only the immutable Task002 compact dataset
and exposes train-only loading, deterministic feature construction, and model
contracts used by the Task003 records.
"""

from .dataset import (  # noqa: F401
    CASE119_DATASET_ID,
    CASE119_DATASET_SCHEMA,
    CompactDatasetVerification,
    TrainingDataset,
    load_training_dataset,
    verify_case119_dataset,
)

