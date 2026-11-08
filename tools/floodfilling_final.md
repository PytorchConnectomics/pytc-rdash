# Floodfilling Final

| Field | Value |
| --- | --- |
| **File** | `floodFilling_final.pdf` |
| **Category** | connectomics |
| **Subcategory** | neuron_segmentation |
| **Authors (guess)** | floodFilling, final |
| **BibTeX key** | `floodfilling` |
| **PDF** | [floodFilling_final.pdf](../../../raw/papers/connectomics/neuron_segmentation/labs/google/FFN/floodFilling_final.pdf) |

## Summary

This paper presents flood-filling networks (FFNs), a novel automated segmentation method for reconstructing neurons from volume electron microscopy data. FFNs use convolutional neural networks with a recurrent pathway that iteratively optimizes and extends individual neuronal processes, achieving a mean error-free neurite path length of 1.1 mm in zebra finch brain tissue—an order of magnitude better than previous approaches. The method addresses the critical bottleneck of requiring extensive human proofreading for neural circuit reconstruction.

## Key Contributions

- Introduction of flood-filling networks (FFNs), a new architecture combining CNNs with recurrent pathways for iterative segmentation that considers object shape plausibility during classification
- Achievement of exceptionally low error rates: mean error-free path length of 1.1 mm and only 4 mergers in 97 mm of test data, representing order-of-magnitude improvement over prior methods
- Development of a predicted object map (POM) mechanism that maintains current predictions and allows the network to make classification decisions based on previously classified voxels
- Demonstration of generalization across multiple species (zebra finch, mouse, and Drosophila) and different EM imaging modalities
- Implementation of automated irregularity detection and tissue classification to handle data artifacts and prevent segmentation errors at large structures

## Methods

- **Flood-filling networks (FFNs)**: Dual-input channel architecture with one channel for 3D image data and one for the predicted object map (POM)
- **Training procedure**: Single-voxel seeding in 49 × 49 × 25 voxel training examples with automatic seed generation at locations distant from cell boundaries; stochastic gradient descent with per-voxel cross-entropy loss
- **Iterative inference**: FOV movement between iterations (±8 voxels laterally, ±4 voxels in Z direction) with automatic position adjustment based on POM values exceeding 0.9 threshold
- **Irregularity detection**: Cross-correlation-based detection of data artifacts like cutting mistakes and alignment errors to prevent supervoxels from spanning irregularities
- **Tissue classification CNN**: Separate network trained to delineate large structures (somata, blood vessels) that differ significantly from typical neurites
- **Merger detection via hysteresis**: Exploitation of reconstruction variability based on seed placement to detect and eliminate merger errors

## Tags

`connectomics` `neuron_segmentation`
