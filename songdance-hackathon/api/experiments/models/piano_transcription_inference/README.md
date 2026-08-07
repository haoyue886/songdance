# Piano Transcription Inference audit

This candidate is an audit record only. It is not installed in the API image, does
not receive a GPU allocation, and must not run fixed-set A/B or human review.

- Source: `qiuqiangkong/piano_transcription_inference@0226e74cbc805660e34bbd6a8fed2083890ebb88`
- Source audit: `setup.py` declares an MIT classifier, but the fixed repository tree
  contains no `LICENSE`, `COPYING`, or `NOTICE` file. A classifier without license text
  is insufficient production-use evidence, so source status is `UNVERIFIED`.
- Weight: `CRNN_note_F1=0.9677_pedal_F1=0.9186.pth` from Zenodo record `4034264`.
  Zenodo declares the record `CC-BY-4.0`; the published metadata exposes an MD5 digest
  but no pinned SHA-256 has been verified locally.
- Training data: neither the candidate repository nor the Zenodo model record names the
  training dataset or gives its license. Status is `UNVERIFIED`.
- Runtime: upstream tested Python 3.7 and PyTorch 1.4.0; it documents CPU and CUDA use.

The production candidate remains blocked with
`SOURCE_LICENSE_TEXT_UNAVAILABLE`. Reopen this audit only after obtaining a source
license text, verified weight SHA-256, and documented production-compatible training
data provenance.
