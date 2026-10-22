"""Compatibility interface; implementation lives in tasks.dataset."""

from benchmarking.tasks.dataset import (
    Dataset,
    case_location,
    core_membership,
    dataset_root,
    index_path,
    load_dataset,
    process_manifest,
    select_core,
)

__all__ = ['Dataset', 'case_location', 'core_membership', 'dataset_root', 'index_path', 'load_dataset', 'process_manifest', 'select_core']
