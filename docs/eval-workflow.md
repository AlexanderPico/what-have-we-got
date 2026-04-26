# eval workflow

1. store local-real images in `local-real-images/` (gitignored)
2. add benchmark manifest entries under `eval/benchmarks/`
3. use `src/whgot/eval.py` helpers to score outputs against the manifest contract
4. compare category accuracy, name accuracy, and key-metadata hit rate
5. grow the benchmark set before changing prompts/models aggressively

Benchmark source mix for this project:
- local real images from home / second-hand-shopping contexts
- synthetic/public examples for broader coverage
