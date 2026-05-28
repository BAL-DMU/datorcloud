# MIRO-on-HF layout (Phase 3 of the DORIS integration plan)

Phase 3 of the [DORIS step-by-step plan](https://github.com/bal-dmu/msk-ai-trust-to-deploy/blob/main/99_integration_plan/STEP_BY_STEP_PLAN.md#5-phase-3--datorcloud--hugging-face-delivery-wk-1012)
makes DatorCloud the **uploader**: every CC-BY-eligible record in an L4
snapshot is published to a Hugging Face dataset repo alongside the
L1-L4 Parquet sidecars. The Hub then becomes the queryable public face
of the same catalog the TRE keeps as the master.

The publisher (`datorcloud.components.HFPublisherComponent`) is invoked
through `DatorCloudOrchestrator.publish_to_hub`. The DORIS-side wrapper
`doris publish` provides a one-line CLI for the same operation.

## Repo layout

See [`datorcloud/templates/catalog_layout.md`](../datorcloud/templates/catalog_layout.md)
for the canonical tree. The short version:

* `README.md`  — HF-conforming dataset card (one config per `dataset_id`).
* `catalog/`   — L1-L4 Parquet sidecars + denormalised `v_doris.parquet`.
* `data/<dataset_id>/<subject_id>/manifest.json` — per-subject pointer.
* `data/<dataset_id>/<subject_id>/image.nii.gz` + `seg/<label>.nii.gz`
  when the caller passes `include_blobs=True`.

## Publish-time license gate (defence in depth)

Before any byte is written, the publisher applies the I5 license gate:

* every L1 row's `license_spdx` MUST be in `allowed_licenses`;
* `redistribution_ok` MUST be True for every published row;
* `share_alike_obligation` must match `require_share_alike` (SA repo /
  CC-BY umbrella); violation raises `LicensePolicyError`;
* `privacy_class` must be in `allowed_privacy` (default
  `('public',)`); DUA / restricted records refuse to publish;
* every DOI in `l1_citations` must appear in the rendered README;
  violation raises `CitationCompletenessError`.

A violation surfaces *before* `HubBackend.upload_file` is called, so a
failed publish never leaves a partial tree behind.

## Backends

The publisher writes through a small `HubBackend` abstraction:

| Backend                | Used by                                              |
|------------------------|------------------------------------------------------|
| `LocalFilesystemHub`   | offline integration tests (`doris-it-03-hf-upload`); |
| `HuggingFaceHub`       | real pushes (`doris publish --dry-run=false`).       |

`LocalFilesystemHub` writes files under a local directory tree and
computes a deterministic revision SHA as the SHA-256 of the sorted
`(path, file_sha256)` listing. This makes the integration test runnable
in CI without an HF account.

## Cross-tier identity (per I6)

The publisher writes the *snapshot payload* (frozen L1/L2/L3 +
`l4_snapshots` row) verbatim. Combined with the deterministic Parquet
encoding, this guarantees:

```
DatorCloudOrchestrator.fetch(snapshot_id=X).catalog_sha256
    == read_parquet('<hub>/catalog/l4_snapshots.parquet').catalog_sha256[0]
    == cohort_builder.build_cohort(snapshot_id=X, source='hf').catalog_sha256
```

This is the system-level invariant `doris-it-04-hf-query` (Phase 4)
asserts.
