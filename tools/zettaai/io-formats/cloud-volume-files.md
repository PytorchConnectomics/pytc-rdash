# cloud-volume, cloud-files (ZettaAI forks)

**GitHub:** https://github.com/ZettaAI/cloud-volume
**Language:** Python | **Status (2026-11-06):** forks of seung-lab; work on branches; last push 2026-08-13

Upstream docs: [../../seung-lab/io-formats/](../../seung-lab/io-formats/). Changes are performance branches by Nico Kemnitz, 2026:

- cloud-volume `perf/thread-local-io`: re-enable multithreading for local precomputed reads/writes, but **only once it pays for itself**; wake `wait()` on a condition variable instead of polling.
- [cloud-files](https://github.com/ZettaAI/cloud-files) `feat/obstore-backend`: **obstore (Rust `object_store`)** backend for `gs://` and `s3://` with credential handling and parity tests; `feat/isal-gzip-backend`: prefer GIL-releasing **isal** over deflate for gzip.
- Supporting forks: [arrow-rs-object-store](https://github.com/ZettaAI/arrow-rs-object-store) (GCS gzip content-length fix), [deflate](https://github.com/ZettaAI/deflate), [tensorstore](https://github.com/ZettaAI/tensorstore), [filesystem_spec](https://github.com/ZettaAI/filesystem_spec), [pyzfp](https://github.com/ZettaAI/pyzfp).

## Takeaway
Cloud I/O, not GPU, is the bottleneck they are attacking: Rust object-store clients and GIL-free decompression. Worth trying if PyTC inference on GCS/S3 precomputed volumes is I/O bound.
