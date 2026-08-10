# Aria-AMT experiment

This directory is an executable isolated environment and is never added to the API
dependency lock.

- Source: `EleutherAI/aria-amt@a1ab73fc901d1759ec3bc173c146b3c6a3040261`
- Audit runtime: Python 3.11, CPU PyTorch 2.4.1, CPU torchaudio 2.4.1
- Inference runtime: NVIDIA CUDA is mandatory in the pinned upstream code; CPU and
  Apple MPS inference are not supported
- Weight: `piano-medium-double-1.0.safetensors` at Hugging Face revision
  `8cc4cf5c83b47f2689ac256a947b2a57c17a4c8b`
- Weight SHA-256: `089d3129dbe93246aeda55efe668c8a48af08afaf9dd15c64cef0a07c0fb30a4`
- Weight license: `CC-BY-NC-SA-4.0`; offline noncommercial evaluation only
- Candidate status: `research_only`; rejected from production-candidate A/B before GPU
  allocation because the fixed weight license does not permit the intended use

Build the isolated CPU audit image from this directory:

```sh
docker build -t songdance/aria-amt:a1ab73f .
```

This image verifies that the fixed source, dependencies, model configuration, and
checkpoint can be loaded without polluting the API environment. It is not an inference
image: the pinned upstream `transcribe()` checks `torch.cuda.is_available()` and the
inference implementation moves the model, audio, and caches directly to CUDA. A real
Inference would require an NVIDIA CUDA host and a CUDA-enabled PyTorch 2.4.1 image, but
SongDance does not schedule that work for this fixed weight. Do not allocate CUDA, run
the fixed-set A/B, or report CPU-image installation/checkpoint loading as a transcription
result unless a separate commercial license is obtained and recorded first.

The Dockerfile also pins `EleutherAI/aria-utils@4ed0749d2d70918610f03a5316bf283479ff9d09`
and the Python runtime dependencies. `fetch_pinned_source.py` downloads only the Python
package and model configuration from the fixed Aria-AMT commit, verifies every Git blob
SHA-1, and excludes the upstream repository's large test-audio fixtures. Mount evaluated
audio and verified weights at runtime; do not copy them into the API image or commit them
to this repository. Inputs must be normalized WAV files produced by the shared SongDance
preprocessing pipeline.

Before running an evaluation, record a full weight revision, SHA-256, HTTPS download
source, weight license, HTTPS license evidence URL, and relative local path in
`../manifest.json`. The precheck script reads the local weight file and rejects a
candidate unless its SHA-256 matches the manifest.
