# analog-db GF180 Cases

**Noncommercial circuit collection.** Circuit derivatives and corresponding
reference layouts retain PolyForm Noncommercial 1.0.0 and the upstream component
terms in [LICENSE](LICENSE) and [NOTICE](NOTICE). Independently authored measurement
decks use the [root MIT license](../../../LICENSE) as identified there. The framework's MIT license does not relicense
these circuit materials. See [repository licensing](../../../LICENSING.md).

Twenty-one qualified public cases use native ICLayout-Bench contracts and independent
reference GDS. They cover regulation, cascoded amplification, resistive
load/feedback behavior, common-mode recovery, temperature-dependent bias and isolated-body startup. Each case has its own
physical checks, candidate-derived RC measurements and calibrated scoring.
Use the shared [GF180 resources](../../../docs/tools.md#gf180).

| Case | Qualified scope | Coefficient |
| --- | --- | ---: |
| [TI-Architecture Error Amplifier](cases/amp_019_ti_ldo_error/README.md) | External bias, full RND/Rz/Cc, follower transfer and loaded response | 6 |
| [Simple Unity-Feedback LDO](cases/ldo_003_analoggym_simple/README.md) | 360-unit pass device, complete compensation/bleed, line/load and startup | 7 |
| [Folded-Cascode LDO](cases/ldo_002_analoggym_folded_cascode/README.md) | Fixed external reference/bias, physical bleed, supply/load perturbations and resistive-load startup | 7 |
| [PMOS LDO with Feedforward Compensation](cases/ldo_007_pmos/README.md) | Complete divider/CFF/RZ/CC, external reference/current bias, supply/load perturbations and startup | 7 |
| [Externally biased PMOS regulator](cases/ldo_004_basic_pmos/README.md) | Supply/load, dropout, load-step and rejection | 7 |
| [Self-Biased Cascode Common-Source Gain Stage](cases/gs_001_cascode_cs/README.md) | Three operating conditions; see the case's explicit limits | 4 |
| [Resistively Loaded Differential Pair](cases/dp_001_resistive_load/README.md) | Three operating conditions; see the case's explicit limits | 4 |
| [Four-Transistor Positive-Temperature-Slope Core](cases/tsn_003_ptat_4t_xcoupled/README.md) | Three operating conditions; see the case's explicit limits | 3 |
| [Externally Biased PMOS-Input Folded-Cascode OTA](cases/amp_004_folded_cascode/README.md) | Three operating conditions; see the case's explicit limits | 5 |
| [Resistive-Feedback Hysteretic Comparator](cases/cmp_001_hyst_diffpair/README.md) | Three operating conditions; see the case's explicit limits | 5 |
| [Tail-Referenced Telescopic Cascode Amplifier](cases/amp_018_telescopic_cascode/README.md) | Tail-relative bias, gain, unity crossing and loaded phase margin | 5 |
| [Segmented-Resistor NMOS Common-Mode Controller](cases/cmfb_003_5t_nmos_input/README.md) | Two physical 5 Mohm sense chains and specified-plant recovery | 6 |
| [Self-Starting Isolated-Body PTAT Core](cases/tsn_002_ptat_classic/README.md) | Output-connected isolated body, physical 20 kohm poly and zero-state startup at 18 supply/temperature/ramp combinations with 100 fF load | 6 |
| [Self-Biased LDO Error Amplifier](cases/amp_032_ti_ldo_error_selfbias/README.md) | Self-bias, loaded AC and unity-buffer transient; 10 pF witness stability limitation disclosed | 6 |
| [Self-Biased LDO Reference Amplifier](cases/amp_033_ti_ldo_ref_selfbias/README.md) | Self-bias, loaded AC and unity-buffer transient | 6 |
| [Buffered-Reference LDO](cases/ldo_005_buffered_ref/README.md) | Independent buffered reference, supply/load regulation, rejection and load step | 7 |
| [StrongARM Dynamic Comparator](cases/cmp_002_strongarm/README.md) | Both decisions at two common modes, reset, delay, slew and supply power | 6 |
| [Tan CLIA amplifier](cases/amp_017_tan_clia/README.md) | 512 MOS, physical compensation R/C; 1.8 V, 2.32803 uA, balanced differential AC and follower error/power; extracted gain loss disclosed | 7 |

The separate
[IHP collection](../../ihp-sg13g2/analog-db/README.md) also includes a compensated follower and differential chopper.
PDK/sizing variants do not automatically count as new topology coverage.

The database DSL, source generators, proprietary-process reference decks,
optimization traces and scoreboard are not runtime dependencies. Ideal bias,
physical passives and operating points are resolved per case. Seven compact-deck cases
materialize exactly a problem, circuit and testbench; the regulator also needs
its distinct transient and dropout decks. The isolated-body PTAT additionally
needs a separate physical CDL and simulator netlist for native device mapping.
The four self-biased amplifier/LDO/StrongARM additions each deliver a problem,
physical CDL, simulator netlist and measurement deck. They require ngspice 45;
see the reproducible thin overlay in the tools guide.
The Tan amplifier additionally separates balanced differential AC from its follower
measurement deck.
References, configurations, reader
results and source notices remain outside standard solver inputs.

The [LICENSE](LICENSE) retains PolyForm Noncommercial and applicable component
terms; [NOTICE](NOTICE) records source attribution and maintained changes.
These circuit materials and witnesses are not covered as a whole by the
framework's MIT license. Retain both files with material distributions.

The analog-db [source screening exclusions](../../ihp-sg13g2/analog-db/README.md#source-screening-exclusions)
also apply to this collection: internal ideal functional macros are excluded;
ordinary bias and test apparatus are not. All twenty-one qualified GF180 cases pass
that source screen.

[tsn_001_ptat_2t](cases/tsn_001_ptat_2t/README.md) is qualified as a two-NMOS temperature-response core. Its complete extracted RC network uses exact branch-current resistor equations to avoid ill-conditioned nodal stamping; independent KCL, bidirectional sweeps and numerical refinement pass. This does not establish linear PTAT or startup behavior.

- [sup_001_vcm_detector](cases/sup_001_vcm_detector/README.md): qualified passive two-resistor average detector, finite source/load impedances, AC and step response.
- [ldo_006_stub](cases/ldo_006_stub/README.md): qualified divider-biased source follower, retaining its source ID without claiming complete LDO regulation.
