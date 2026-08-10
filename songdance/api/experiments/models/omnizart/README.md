# Omnizart piano audit

This candidate is an audit record only. It is not installed in the API image, does
not receive a GPU allocation, and must not run fixed-set A/B or human review.

- Source: `Music-and-Culture-Technology-Lab/omnizart@bcd8cb44d4da66ce87df10b6abee5c35a8cc2886`
- Source audit: the pinned repository's `LICENSE` is MIT. This verifies the source
  code only, not the separately distributed model checkpoint or its training data.
- Model provenance: the pinned `paper.md` documents that the piano model was trained
  on MAESTRO. `omnizart download-checkpoints` retrieves a released checkpoint set;
  the project changelog identifies release `checkpoints-20211001`.
- Weight audit: the release does not provide a production-use license, a fixed asset
  revision, or a verified SHA-256 for the piano checkpoint. Its status is
  `UNVERIFIED`.
- Training-data audit: the MAESTRO training statement does not establish that this
  released checkpoint can be used for SongDance's target production use. Its status is
  `UNVERIFIED` pending an auditable license chain.

The candidate is blocked with
`WEIGHT_AND_TRAINING_DATA_LICENSE_UNVERIFIED`. Do not create an isolated runtime,
download checkpoints, allocate a GPU, or run the fixed-set A/B until the checkpoint
license, fixed artifact digest, and production-compatible training-data provenance are
recorded in `../manifest.json`.
