# Broadband SiGe PAM4 Current-Steering Driver

## Overview

This **qualified benchmark case** preserves the upstream layout signoff point:
twelve three-finger HBTs in three cascode current-steering cells, physical
resistors/MIM capacitors, 4 V supply, 3.35 V cascode bias, 1.9 V input common
mode and three external 15 mA tail sinks. The generated simulator netlist is
byte-identical to the pinned upstream signoff netlist. Native LVS packaging
only adds the resistor substrate terminals already present in that simulator
netlist and translates HBT geometry notation to `we/le/Nx`.

The supplied reference layout passes native DRC/LVS and candidate-derived CC/RF
evaluation. Qualification establishes a reproducible benchmark case, not
compliance with every upstream product specification. Electrical performance is
scored continuously against independently simulated source observations. No
core circuit or geometry was retuned. The separate upstream static point
(3.25 V cascode, 16 mA per cell) remains outside this executable task.

## Files

- [Schematic](materials/schematic.svg): digest-bound circuit drawing, excluded from solver inputs.

| File | Role |
| --- | --- |
| [problem.md](problem.md) | Complete solver contract and scoring |
| [case.toml](case.toml) | Qualified case, inputs, gates and tool bindings |
| [materials/circuit.cdl](materials/circuit.cdl) | Physical LVS authority |
| [materials/circuit.spice](materials/circuit.spice) | Same-geometry source simulation |
| [materials/testbench.spice](materials/testbench.spice) | OP, two input AC drives, output AC drive and tone transient |
| [reference/pam4drv_pam4_lay.gds](reference/pam4drv_pam4_lay.gds) | Faithfully regenerated upstream physical witness |
| [materials/provenance.json](materials/provenance.json) | Fixed source commit and original-file identities |
| `materials/upstream/` | Original source records, including distinct static/layout versions; maintainer-only |

Development sources, immutable upstream code, dependency locks, generation and
staging scripts live in ICLayout-Designs. Bench consumes only static deliveries.

## Reference Results

Independent local validation uses ngspice 45 (`hsa`), KLayout 0.30.11 and
KPEX 0.3.12. Native DRC has zero unwaived violations, strict-port LVS passes,
and candidate-bound CC extraction retains 12 HBTs, 12 resistors, 3 MIMs and
131 parasitic capacitors. Physical dimensions are approximately 99.6 × 75.8 µm.
These are local results, not a restatement of upstream signoff claims.

| Metric | Unit | Pre-layout | Post-layout |
| --- | --- | --- | --- |
| LSB gain at 1 GHz | dB | 2.336826 | 2.336648 |
| MSB gain at 1 GHz | dB | 8.312464 | 8.312163 |
| Binary weight | dB | 5.975638 | 5.975515 |
| LSB relative gain at 50 GHz | dB | −0.915497 | −1.302350 |
| MSB relative gain at 50 GHz | dB | −1.711800 | −2.293190 |
| S11 at 32 GHz | dB | −11.286680 | −9.933024 |
| S22 at 50 GHz | dB | −14.487080 | −9.223511 |
| Supply power | mW | 179.0668 | 179.0668 |
| Fundamental differential swing | V | 2.739725 | 2.739743 |

The reproduced upstream sampled-sweep calculation reports MSB bandwidth
58.56 GHz and worst sampled S11 below 32 GHz of about −10.01 dB. That grid
ends at **31.623 GHz** before 32 GHz. Likewise the last sample below 50 GHz
is **44.668 GHz**, where S22 is about −10.125 dB. It is not the
50 GHz endpoint. Separate single-frequency checks confirm the values at 32 GHz
(−9.92735 dB) and 50 GHz (−9.22221 dB), so interpolation does not explain them.
These differences from the upstream −10 dB target affect continuous quality;
that target is not a Bench acceptance gate.

KPEX blackboxing preserves native MIM dimensions and connectivity. The upstream
layer-stripping/reinsertion flow was independently reproduced as a diagnostic;
qualification does not rely on its source-derived capacitor reconstruction.
This contract covers nominal CC and the declared RF/tone checks, not distributed
wire resistance, inductance, eye/RLM or manufacturing signoff. The existing
Magic/HBT RC route is not used for these results.

The coefficient is 4: a compact feedforward circuit coupling weighted gain,
return loss, physical passives and output loading. The 10000 µm² area anchor
allows approximately 4500 µm² for three device rows, 2000 µm² for terminations
and loads, and 3500 µm² for routes, vias and substrate access. It is not fitted
to the submitted witness area. Source-paired electrical quality are specified in the problem. Power and swing retain nonnegative physical
domains; finite gain, bandwidth and return-loss observations have no arbitrary
product-specification gate. Binary weight uses the ideal doubling interval
`20*log10(2)` dB as its normalization scale, independent of this layout.

The independently evaluated witness has electrical quality `E = 0.959258`,
functional area `7551.672 µm²`, area quality `Q = 1.324210` and score
**112.705767**. Response quality is `0.882704`; this records the extracted RF
performance cost while the compact footprint improves area quality. The score
is uncapped and qualification does not imply a 100-point electrical result.

## Reproduce

Follow the shared [tool setup](../../../../../docs/tools.md#image-development).
Build the ngspice overlay, then synchronize the locked Python tools:

```bash
docker build -f Dockerfile.ngspice --build-arg BASE_IMAGE=iclayout-bench-tools:local \
  -t iclayout-bench-tools:ngspice45 .
docker build -f Dockerfile.dev --build-arg BASE_IMAGE=iclayout-bench-tools:ngspice45 \
  -t iclayout-bench-tools:pam4 .
uv run --locked python -m benchmarking.engine.preview prepare \
  --case drv_001_pam4_sige_dac --image iclayout-bench-tools:pam4 \
  --output build/pam4-prepared
uv run --locked python -m benchmarking.engine.cli evaluate \
  build/pam4-prepared/case/case.toml \
  tasks/ihp-sg13g2/analog-db/cases/drv_001_pam4_sige_dac/reference/pam4drv_pam4_lay.gds \
  --output build/runs/pam4-reference
```

Use fresh output directories. These commands generate the identity-bound report,
raw simulator data, native rule evidence and extracted circuit. Expect physical
validity, completed electrical evaluation and source-paired quality/area scoring.
A lower RF quality value is a measured layout cost, not failure to reproduce an
upstream performance promise. Tool errors, invalid evidence and physical
rejection retain their usual distinct meanings.

## Source and License

From the [fixed upstream circuit](https://github.com/MacAnalog/spicexplorer-release/tree/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/drv_001_pam4_sige_dac); retain the collection [LICENSE](../../LICENSE) and [NOTICE](../../NOTICE).
