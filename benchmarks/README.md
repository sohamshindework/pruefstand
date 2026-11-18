# CrashBench v1

`crashbench-v1.json` declares the executable, synthetic fixture protocol. Task definitions are packaged at `src/pruefstand/data/enterprise-de.json`. `baseline.json` is the generated idempotent-agent profile used by CI; `vulnerable.json` is the comparison profile. They contain actual observed fixture scores, not ratings of external agents.

Regenerate from the repository root with `python scripts/reproduce.py`. The default experiment is two agents × eight tasks × 21 conditions × five repeats = 1,680 runs. Scores/verdicts are deterministic; timestamps and measured local durations differ. Regeneration intentionally updates the baseline and must be reviewed. CI only compares, never accepts new baselines automatically.

Balanced fault frequencies in this suite are stress-test weights, not estimates of production incident rates. Eight task templates are insufficient for broad reliability claims. See `docs/methodology.md` for the exact metrics, bootstrap sampling, and caveats.
