# Data Versioning & Reproducible Experiments (DVC)

DVC gives the platform **data lineage** and **reproducibility** (a Tower ML-Engineer
requirement): datasets and model outputs are versioned alongside git, and any
experiment can be reproduced exactly from its inputs.

## One-time setup

```bash
pip install dvc            # already in backend/requirements.txt
dvc init                   # creates .dvc/ (commit it)
```

## Track a dataset

```bash
mkdir -p data
# put prices.csv in data/   (e.g. python scripts/make_test_data.py then copy one in)
dvc add data/prices.csv     # creates data/prices.csv.dvc (commit that, not the CSV)
git add data/prices.csv.dvc data/.gitignore && git commit -m "track dataset"
```

## Reproducible run

`dvc.yaml` defines a `research` stage that runs the toolkit CLI with `params.yaml`.

```bash
dvc repro                  # re-runs ONLY if data/code/params changed; records hashes
cat out/report.json        # Sharpe, drawdown, CV scores, winner
```

Change a hyperparameter in `params.yaml`, run `dvc repro`, and DVC re-executes the
stage and records the new lineage. `dvc metrics show` / `dvc params diff` compare runs.

## Remote storage (share data without bloating git)

```bash
dvc remote add -d storage s3://your-bucket/automl   # or gs://, azure://, ssh://
dvc push                                            # upload data + outputs
dvc pull                                            # teammate fetches them
```

## What's tracked where

| Tracked by git | Tracked by DVC |
|---|---|
| code, `dvc.yaml`, `params.yaml`, `*.dvc` pointer files | datasets (`data/`), run outputs (`out/`) |

Git stays small; DVC handles large/binary data with content-addressed hashes, so a
commit + its `.dvc` files fully pin the data a result came from.
