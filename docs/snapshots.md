# L4 cohort snapshots

A **snapshot** is the immutable identity of one cohort selection. It
captures every L1-L3 row that matched the selecting predicate at freeze
time, hashes that frozen payload into `catalog_sha256`, and stores both
the blob and the hash in `l4_cohort_snapshot`. The same predicate
re-evaluated tomorrow against a mutated catalog will produce a
**different** `snapshot_id` (and likely a different hash) -- that is the
point. Two snapshots taken minutes apart against an unchanged catalog
produce **identical** hashes -- also the point.

This page describes the freeze semantics, the canonical serialisation
rule, and the join surface that `l4_eval_set` exposes for the
T2D inter-observer evaluation pipeline.

## 1. Freeze semantics

```python
from datorcloud.snapshots import snapshot_cohort

snap = snapshot_cohort(
    catalog,
    dataset_id="totalsegmentator",
    predicate_sql="modality = 'CT' AND 'pelvis' = ANY(body_part)",
    snapshot_date="2026-05-27",
)
print(snap.snapshot_id)        # totalsegmentator@2026-05-27
print(snap.catalog_sha256)     # 64-character hex sha-256
print(snap.n_records)          # number of distinct record_uids
```

Internally `snapshot_cohort()`:

1. Evaluates `predicate_sql` against `v_doris` to enumerate the matching
   `record_uid`s.
2. Reads the full L1, L2, and L3 rows for those `record_uid`s into a
   single long-format DataFrame with a `layer` discriminator column.
3. Drops `l2_sensor.converted_uri` and `l1_experiment.ingested_at` from
   the payload -- these are observability fields that may legitimately
   mutate without altering the cohort identity (see §3 below).
4. Computes `catalog_sha256` as the SHA-256 of the *canonical JSON*
   serialisation of the payload (columns alphabetised, rows sorted
   lexicographically, lists encoded as JSON arrays, timestamps in ISO
   8601, NaN/NaT normalised to `null`).
5. Serialises the same payload to a Parquet blob and writes
   `(snapshot_id, catalog_sha256, n_records, schema_version,
   l13_payload)` into `l4_cohort_snapshot`. `hf_publication_log` is
   reserved for Phase 3.

The Parquet blob is the storage format; the canonical JSON is what gets
hashed. This split lets us optimise blob compression independently from
the deterministic identity, and avoids the well-known PyArrow-version
sensitivity of Parquet byte-level reproducibility.

## 2. Reconstructing the payload

```python
from datorcloud.snapshots import load_snapshot_payload

frozen = load_snapshot_payload(catalog, snap.snapshot_id)
l1 = frozen[frozen["layer"] == "l1_experiment"]
l3 = frozen[frozen["layer"] == "l3_annotation"]
```

The `(F)` operator (`DatorCloudOrchestrator.fetch`) and Phase 3's HF
publisher both call `load_snapshot_payload` so downstream materialisation
reads exactly the rows captured at snapshot time -- never the live
tables. This is what guarantees the cross-tier identity gate in Phase 4
(`build_cohort(source='hf').catalog_sha256 == build_cohort(source='minio').catalog_sha256`).

## 3. Why `catalog_sha256` is insensitive to `converted_uri` writes

After ingest, the raw -> NIfTI/Zarr conversion stage runs asynchronously
and back-fills `l2_sensor.converted_uri` for each record. That URI is
*provenance*, not *identity*: the same record converted on a different
day still represents the same imaging examination.

The snapshot freeze deliberately drops `converted_uri` from the
canonical payload before hashing. Two snapshots of the same predicate
-- one taken before the conversion stage runs, one taken after -- yield
identical `catalog_sha256` values, which is the gate
`doris-it-01-catalog` assertion (c) verifies:

```python
first = snapshot_cohort(catalog, dataset_id="ts", snapshot_date=today)

catalog.update_l2_converted_uri(
    record_uid="u_s1000", modality="CT", sequence="",
    converted_uri="s3://orx-datalake/ts/s1000/ct.zarr",
)

second = snapshot_cohort(catalog, dataset_id="ts", snapshot_date=today)
assert first.catalog_sha256 == second.catalog_sha256
```

## 4. Eval-set orthogonality (design invariant I3)

A snapshot is *what data* you selected. An eval set is *how you score
it* (which annotator columns to consult, which labels to evaluate,
which inter-observer quantiles to use). The two are independent: one
snapshot may carry multiple eval sets.

```python
from datorcloud.snapshots import create_eval_set

create_eval_set(
    catalog,
    eval_set_id="pelvis_femur_v3",
    snapshot_id=snap.snapshot_id,
    annotator_columns=["radiologist_a", "radiologist_b"],
    target_labels=["femur_left", "femur_right"],
    inter_observer_quantiles=[0.25, 0.75],
)

create_eval_set(
    catalog,
    eval_set_id="pelvis_femur_v3_q10_q90",
    snapshot_id=snap.snapshot_id,            # same snapshot, different quantiles
    annotator_columns=["radiologist_a", "radiologist_b"],
    target_labels=["femur_left", "femur_right"],
    inter_observer_quantiles=[0.1, 0.9],
)
```

The Phase 5 evaluation pipeline joins
`l4_eval_set -> l4_cohort_snapshot` to recover both the data identity
(`catalog_sha256`) and the scoring layout in a single query. The
integration-test gate `doris-it-05-evaluation` assertion (f) exercises
exactly this join.

## 5. Versioning

The `schema_version` stamped into every `l4_cohort_snapshot` row is the
DDL version from `datorcloud/schemas/__init__.py::SCHEMA_VERSION`. A
breaking change to the L1-L4 DDL bumps the major component and forces
a `catalog_sha256` recomputation for every downstream consumer. Per the
plan, that has not happened since 1.0.0 and is not expected before v2
of the integration plan.
