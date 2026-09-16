# analog-db IHP Cases

The [catalog](catalog.toml) indexes twenty-four qualified native ICLayout-Bench cases.
Each ships fixed circuit materials, an independent physical witness and
candidate-derived RC measurements. Running them does not require SpiceXplorer
or its source checkout.

| Case | Circuit role | Scope |
| --- | --- | --- |
| [amp_001_5t](cases/amp_001_5t/README.md) | Five-transistor OTA plus bias mirror | 1.5 V, 20 uA reference, 10 pF, TT, 27 C |
| [buf_001_super_follower](cases/buf_001_super_follower/README.md) | Local feedback with internal physical MIM compensation | 0.55–0.65 V input, 5/10/20 pF, source/RC gain and step recovery |
| [sw_002_chopper_diff](cases/sw_002_chopper_diff/README.md) | Eight-MOS differential polarity commutation | Both input polarities and clock states, Ron, loaded switching and clock injection |
| [cmfb_004_output_switched_cap](cases/cmfb_004_output_switched_cap/README.md) | Four-MIM sampled common-mode sensing | Five conditions, sampled error, hold drift and supplied clock energy; driven inputs, not amplifier-loop stability |
| [sw_003_binary_capbank](cases/sw_003_binary_capbank/README.md) | Three-bit 1:1:2:4 MIM capacitive transfer | All eight static codes, AC/step error and return/settling; no live code-change redistribution |
| [amp_024_smcnr](cases/amp_024_smcnr/README.md) | Two-stage OTA with physical series nulling R/C | 1.2 V, 100 nA external bias, 5/10/20 pF loop gain and sustained step recovery |
| [amp_023_fer_fd2s](cases/amp_023_fer_fd2s/README.md) | Fully differential two-stage OTA with physical compensation and transistor CMFB | Six load/polarity conditions: differential return ratio, common-mode transfer, coupled step recovery and output-current disturbances |
| [ia_006_fan_chopper_cmfb](cases/ia_006_fan_chopper_cmfb/README.md) | Complete clocked capacitive IA with transistor CMFB and retuned physical compensation | Four load/polarity conditions at 20 kHz: period-mean transfer/recovery, full ripple, summing-node error, common-mode regulation and supplied clock energy |
| [smp_001_nmos_th](cases/smp_001_nmos_th/README.md) | NMOS sampler with physical 499.772 fF storage | Sixteen input/temperature/off-state-input conditions: acquisition, pedestal, isolated-input feedthrough, 10 us drift and reacquisition |
| [amp_003_fan_smc](cases/amp_003_fan_smc/README.md) | Single-capacitor three-stage OTA with active output feedforward | Preserved 412 fingers, separate source-tied input well, disclosed 3 uA bias; 5/10/20 pF loop gain and 3 us sustained recovery |
| [amp_008_leung_nmcf](cases/amp_008_leung_nmcf/README.md) | Two output-connected compensation capacitors around three stages | Rounded grid, three physical MIM units, 5/10/20 pF return ratio and finite-step recovery |
| [amp_009_leung_nmcnr](cases/amp_009_leung_nmcnr/README.md) | Two capacitors feeding a shared series nulling resistor | Bias-controlled output PMOS, physical junction resistor, 5/10/20 pF; 20 pF overshoot remains explicit |
| [amp_002_alfio_raffc](cases/amp_002_alfio_raffc/README.md) | Current-buffer compensation with an active feedforward path | Source-side cascode compensation, maintained fingering, four MIM units and 5/10/20 pF loop/recovery checks |
| [amp_005_hoilee_affc](cases/amp_005_hoilee_affc/README.md) | Six-MOS current-buffer compensation branch | Seven MIM units, disclosed 3.15498 uA bias, 5/10/20 pF return ratio and 3 us sustained recovery |
| [amp_010_peng_acbc](cases/amp_010_peng_acbc/README.md) | Three-MOS auxiliary compensation termination | Six MIM units, disclosed 1.80825 uA bias, 5/10/20 pF and 30 us sustained recovery |
| [ldo_008_fer_mirror_ota](cases/ldo_008_fer_mirror_ota/README.md) | Mirror-OTA regulator with physical divider and 160 pF series compensation | 1.2/1.3 V, 0.5 V reference; bilateral return ratio including multiple crossings, line/load/headroom, zero-state startup and fast/large load recovery |
| [ldo_009_fer_5t_pass](cases/ldo_009_fer_5t_pass/README.md) | Complete unity-feedback regulator with internal COUT | 29 fingers, 18 MIM and five poly segments; 1.2/1.3 V, line/load/headroom, return ratio, current-load recovery and specified resistive startup |
| [trm_001_vcr](cases/trm_001_vcr/README.md) | Physical resistor pullup and NMOS shunt trim | Approximately 200 kohm internal pullup; 1.1/1.3 V, 27/85 C, two loads, monotonic sweep, nonlinear conductance and recovery |
| [amp_007_leung_dfcfc2](cases/amp_007_leung_dfcfc2/README.md) | Miller compensation across a separate auxiliary PMOS stage | Retained 440 fingers and 20 uA bias, ten MIM units, 5/10/20 pF loop and 3 us recovery; explicit nonlinear iteration ceiling |
| [amp_006_leung_dfcfc1](cases/amp_006_leung_dfcfc1/README.md) | Auxiliary NMOS controlled by the output NMOS gate, with separate internal compensation termination | 675 maintained fingers, eleven MIM, disclosed 6.86885 uA bias; both 0.5/0.7 V operating points, bilateral return ratio and 3 us sustained recovery at 5/10/20 pF |

| [amp_012_peng_tcfc](cases/amp_012_peng_tcfc/README.md) | Source-driven auxiliary PMOS path with separate net10 output control | 108 MOS, three MIM including added local compensation; 1.2 V, 5/10/15 pF, bilateral loop and sustained 200 mV recovery |

| [amp_015_sau_cfcc](cases/amp_015_sau_cfcc/README.md) | Input-driven PMOS active feedforward at the intermediate control node | 225 MOS, 17 MIM including 16 pF local and 48 pF output storage; 1.2 V, 5/10/15 pF external load, bilateral loop and sustained recovery |

| [ldo_001_analoggym_basic](cases/ldo_001_analoggym_basic/README.md) | Folded/cascoded error amplifier with auxiliary pass-gate drive and physical 3:1 divider | 831 MOS, four MIM, sixteen poly; 0.225 V reference, 1.2/1.3 V supply, 200 ns load edges and 10/20 us zero-state ramps; explicit faster-edge failures |

| [vref_001_vgs](cases/vref_001_vgs/README.md) | Mixed LV/HV two-transistor reference | 1.0–1.5 V, −20–85 C typical-model samples, ±1 pA loading, zero-state ramp and sustained recovery; no precision-reference claim |

The OTA is a conversion pilot related to the existing GF180 OTA family.
The buffer adds physical compensation and loaded local-feedback measurements;
the chopper adds differential commutation and driven-input clock feedthrough.
PDK and sizing variants do not automatically add topology coverage.

Materials retain PolyForm Noncommercial and applicable Apache/MIT/BSD component
terms in [LICENSE](LICENSE) and [NOTICE](NOTICE). The ferrosim component record
distinguishes retained author attribution and standard MIT terms from an
original copyright notice that was not independently retrieved. The framework
MIT license does not replace these circuit/material terms.

Follow each case's reproduction commands and the shared
[tool setup](../../../docs/tools.md). Only the declared problem, physical
netlist, equivalent simulator representation and measurement deck enter a
standard solve. References, reader results, source records, licenses and host
configuration remain outside solver inputs. Retain collection LICENSE and
NOTICE with material distributions.
