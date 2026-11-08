# open-data-registry (E11 fork)

**GitHub:** https://github.com/e11bio/open-data-registry
**Fork of:** [awslabs/open-data-registry](https://github.com/awslabs/open-data-registry) (1765★)
**Language:** Python (validators) + YAML | **Stars:** 0 | **License:** Apache-2.0
**Divergence:** 0 ahead, 1819 behind (forked 2025-05-21, last push 2025-09-22)

The AWS Open Data registry: one YAML file per public dataset, rendered at
https://registry.opendata.aws. E11 forked it to submit the PRISM dataset entry
(`s3://e11bio-prism`) upstream via PR — the fork itself carries no retained changes and is now
far behind.

## Dataset entry format
```yaml
Name: E11 Bio PRISM Dataset
Description: ...
Documentation: https://github.com/e11bio/e11-open-data
Contact: ...
ManagedBy: ...
UpdateFrequency: ...
Tags: [aws-pds, life sciences, neuroscience, imaging]
License: CC BY-SA 4.0
Resources:
  - Description: PRISM imaging data, segmentations and annotations
    ARN: arn:aws:s3:::e11bio-prism
    Region: us-east-1
    Type: S3 Bucket
DataAtWork:
  Tutorials: [...]
  Publications: [...]
```

## Relevance to PyTC
Only as a template: this is the exact mechanism for getting a lab dataset hosted free on AWS
Open Data with a public landing page — relevant if the lab publishes its own large annotated EM
volumes. See [e11-open-data](e11-open-data.md) for what the resulting bucket looks like in
practice.
