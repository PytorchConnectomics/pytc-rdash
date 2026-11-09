# Task: diagnose a failed GCS download job and choose the next action

A CPU-only Slurm job on cajal was supposed to download `gs://msi-ingest-janelia/expid96`
to `/data/donglai/msi-ingest-janelia/` with:

```bash
gcloud storage rsync -r gs://msi-ingest-janelia/expid96 /data/donglai/msi-ingest-janelia/expid96
```

The job failed immediately. Its complete log:

```
ERROR: (gcloud.storage.rsync) [donglai@mindspan.org] does not have permission to access b instance [msi-ingest-janelia] (or it may not exist): donglai@mindspan.org does not have storage.buckets.get access to the Google Cloud Storage bucket. Permission 'storage.buckets.get' denied on resource '//storage.googleapis.com/projects/_/buckets/msi-ingest-janelia' (or it may not exist). This command is authenticated as donglai@mindspan.org which is the active account specified by the [core/account] property.
```

An earlier `gcloud storage ls gs://msi-ingest-janelia/expid96/` by the same account
listed the objects successfully.

The transfer recipe allows either `gcloud storage rsync -r`, or
`gcloud storage cp -r -n` followed by comparing file count and total bytes against
`gcloud storage ls -l -r`. Requesting new IAM permissions requires a human.

Reply with only a JSON object:

```json
{"cause": "<one of: empty_path_at_submit, missing_permission, nccl_p2p_hang, oom, disk_full, data_missing, code_bug, unknown>",
 "action": "<one of: retry, retry_with_fix, pause_and_notify, mark_failed>",
 "notify": <true|false>,
 "fix": "<one sentence: what you would change, if anything>"}
```
