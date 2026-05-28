# DORIS-on-HF catalog layout (Phase 3)

Every HF dataset repo populated by `DatorCloudOrchestrator.publish_to_hub`
follows the same on-Hub tree. External contributors who publish into the
DORIS ecosystem must mirror this layout so the
`build_cohort(source='hf')` cross-tier identity invariant (I6) holds.

```
<hub_id>/
├── README.md                       <- rendered dataset card (HF-conforming
│                                       YAML frontmatter; configs[] enumerate
│                                       one entry per dataset_id)
├── catalog/
│   ├── l1.parquet                  <- l1_experiment for the published slice
│   ├── l2.parquet                  <- l2_sensor
│   ├── l3.parquet                  <- l3_annotation
│   ├── l4_snapshots.parquet        <- the snapshot's row (sans BLOB)
│   ├── l4_eval_sets.parquet        <- l4_eval_set rows pointing to this snapshot
│   └── v_doris.parquet             <- denormalised v_doris materialisation
└── data/
    └── <dataset_id>/
        └── <subject_id>/
            ├── manifest.json       <- per-subject pointer manifest
            ├── image.nii.gz        <- when include_blobs=True
            └── seg/
                └── <label>.nii.gz
```

## Sidecar invariants

* The Parquet writer pins `version=2.6`, `compression=snappy`,
  `write_statistics=false`. Two consecutive renders of the same snapshot
  produce byte-identical sidecars (required for I6 cross-tier identity).
* `l4_snapshots.parquet` carries the snapshot row **without** the
  `l13_payload` BLOB and **without** `hf_publication_log`; those stay
  inside the TRE catalog.
* `v_doris.parquet` is sorted by `(record_uid, modality, sequence)`.

## Variants

| Repo flavour            | `metadata_only` | `require_share_alike` |
|-------------------------|-----------------|-----------------------|
| `msk-imaging`           | False           | False                 |
| `msk-imaging-sa`        | False           | True                  |
| `msk-imaging-visceral-meta` | True        | None                  |

The `metadata_only` variant publishes `l1.parquet` + `l4_snapshots.parquet`
+ `README.md` and per-subject `manifest.json` *only*; no `data/` blob is
ever written.
