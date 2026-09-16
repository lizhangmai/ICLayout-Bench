# analog-db GF180 Cases

Nine qualified public cases use native ICLayout-Bench contracts and independent
reference GDS. They cover regulation, cascoded amplification, resistive
load/feedback behavior, common-mode recovery, temperature-dependent bias and isolated-body startup. Each case has its own
physical checks, candidate-derived RC measurements and calibrated scoring.
Use the shared [GF180 resources](../../../docs/tools.md#gf180).

| Case | Qualified scope | Coefficient |
| --- | --- | ---: |
| [Externally biased PMOS regulator](cases/ldo_004_basic_pmos/README.md) | Supply/load, dropout, load-step and rejection | 7 |
| [Self-Biased Cascode Common-Source Gain Stage](cases/gs_001_cascode_cs/README.md) | Three operating conditions; see the case's explicit limits | 4 |
| [Resistively Loaded Differential Pair](cases/dp_001_resistive_load/README.md) | Three operating conditions; see the case's explicit limits | 4 |
| [Four-Transistor Positive-Temperature-Slope Core](cases/tsn_003_ptat_4t_xcoupled/README.md) | Three operating conditions; see the case's explicit limits | 3 |
| [Externally Biased PMOS-Input Folded-Cascode OTA](cases/amp_004_folded_cascode/README.md) | Three operating conditions; see the case's explicit limits | 5 |
| [Resistive-Feedback Hysteretic Comparator](cases/cmp_001_hyst_diffpair/README.md) | Three operating conditions; see the case's explicit limits | 5 |
| [Tail-Referenced Telescopic Cascode Amplifier](cases/amp_018_telescopic_cascode/README.md) | Tail-relative bias, gain, unity crossing and loaded phase margin | 5 |
| [Segmented-Resistor NMOS Common-Mode Controller](cases/cmfb_003_5t_nmos_input/README.md) | Two physical 5 Mohm sense chains and specified-plant recovery | 6 |
| [Self-Starting Isolated-Body PTAT Core](cases/tsn_002_ptat_classic/README.md) | Output-connected isolated body, physical 20 kohm poly and zero-state startup at 18 supply/temperature/ramp combinations with 100 fF load | 6 |

The separate
[IHP collection](../../ihp-sg13g2/analog-db/README.md) also includes a compensated follower and differential chopper.
PDK/sizing variants do not automatically count as new topology coverage.

The database DSL, source generators, proprietary-process reference decks,
optimization traces and scoreboard are not runtime dependencies. Ideal bias,
physical passives and operating points are resolved per case. Seven compact-deck cases
materialize exactly a problem, circuit and testbench; the regulator also needs
its distinct transient and dropout decks. The isolated-body PTAT additionally
needs a separate physical CDL and simulator netlist for native device mapping.
References, configurations, reader
results and source notices remain outside standard solver inputs.

The [LICENSE](LICENSE) retains PolyForm Noncommercial and applicable component
terms; [NOTICE](NOTICE) records source attribution and maintained changes.
These circuit materials and witnesses are not covered as a whole by the
framework's MIT license. Retain both files with material distributions.
