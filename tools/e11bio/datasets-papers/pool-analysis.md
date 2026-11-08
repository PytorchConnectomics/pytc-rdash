# pool-analysis

**GitHub:** https://github.com/e11bio/pool-analysis
**Language:** Jupyter Notebook / Python / shell | **Stars:** 0

Wet-lab QC pipeline: analyzes **Nanopore sequencing of AAV viral pools** to check library
balance before the pool is used for barcoding. Handles both extracted viral genomes (capsid
digested, adapters ligated to the ITRs) and the linearized input plasmids. Data comes from
Plasmidsaurus AAV / Premium PCR sequencing.

## Pipeline
Input: a FASTQ of Nanopore reads + FASTA files describing every *expected* variant
(alignment to a known reference rather than de-novo calling).

Output:
1. Reads mapped per variant + aligned read counts (library balance)
2. Variants carrying a mutation relative to the expected sequence (observed ≥2× by default)
3. Truncated, non-full-length AAV products (WIP)
4. Genome orientation, for recombination cassettes (planned)

## Layout
`src/`: `make_combined_ref.py` (build the combined reference), `mapping_and_var_balance.sh`
(minimap2 → samtools → balance), `annotate_variants.py`, `variant_balance.py`,
`call_variants_docker.sh`.
`examples/multibit/`: `calculate_multibit_dist.py`, `simulate_draws.py` — barcode-draw
simulation over the measured pool composition.
`utils/`: `convert_csv_fas.py`, `organize_data.py`, `single_bit_plots.py`, `simulate_draws.py`.
`data/`: reference FASTAs — `egfp`, `itr_left`/`itr_right`, `loxp`, `lox2272`,
`enhancer_promoter_intron`, `polya_wpre`.
`notebooks/`: FLEX recombination analysis.

## Install
```bash
conda create -n pool_analysis && conda activate pool_analysis
conda install pip && pip install -r requirements.txt
brew install minimap2 samtools bcftools seqkit     # macOS
sudo apt install minimap2 samtools bcftools seqkit # Ubuntu/WSL
```

## Relevance to PyTC
Not a connectomics tool — it is upstream molecular-biology QC. Worth one read for context: the
measured pool imbalance from this step is the input distribution that
[combinatorics_dash](combinatorics_dash.md) and
[Preprint-Barcode-Analysis](Preprint-Barcode-Analysis.md) use, so a skewed viral pool
propagates all the way to barcode collision rates in the image. If the lab ever collaborates
on barcode-based reconstruction, this is where "why are some barcodes so much more common"
gets answered.
