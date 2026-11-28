# Taxonomy v3 Vision Evaluation

This directory contains the tracked evaluation protocol and evidence for the full
8-major / 33-subcategory taxonomy.

## Tracked

- `dev_manifest.v3.json` and `frozen_test_manifest.v3.json`
- prompt snapshots and `prompt_manifest.v3.json`
- scoring scripts, metric JSON files and raw model predictions
- manifest integrity tests

## Local-only assets

The raw images (`images/`, `frozen_images/`), open-source candidates and review
previews are intentionally excluded from Git because they exceed 500 MB. The
manifests retain SHA-256, dHash and source provenance. When assets are absent,
the manifest test still validates taxonomy coverage, split isolation and frozen
metadata, then skips only the local file-existence assertion.

Use `harvest_open_sources.py`, `curate_pool_candidates.py`,
`build_v3_manifest.py` and `split_and_freeze_v3.py` to reconstruct local assets
from the recorded sources.
