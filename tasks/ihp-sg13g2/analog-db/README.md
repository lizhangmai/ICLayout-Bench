# analog-db IHP Cases

**Noncommercial circuit collection.** Circuit derivatives and corresponding
reference layouts retain PolyForm Noncommercial 1.0.0 and the upstream component
terms in [LICENSE](LICENSE) and [NOTICE](NOTICE). Independently authored measurement
decks use the [root MIT license](../../../LICENSE) as identified there. The framework's MIT license does not relicense
these circuit materials. See [repository licensing](../../../LICENSING.md).

The [catalog](catalog.toml) indexes forty-one qualified native ICLayout-Bench
cases. They ship independent physical witnesses and candidate-derived parasitic
measurements. PAM4 uses the faithfully reproduced upstream signoff circuit and
layout with native CC/RF evaluation; the other cases declare their RC scope.
Performance is scored against same-condition source simulation. Qualification
does not certify upstream product specifications. Running these cases does not
require SpiceXplorer or its source checkout.

| Case | Circuit role | Scope |
| --- | --- | --- |
| [cmfb_002_5t_pmos_input](cases/cmfb_002_5t_pmos_input/README.md) | Standalone self-biased detector/controller | Positive CM / negative reference DC and AC slopes, differential residual and loaded dynamics |
| [sw_001_transmission_gate_pair](cases/sw_001_transmission_gate_pair/README.md) | Two-MOS bidirectional switch | Three common modes, both directions, finite-drop Ron, leakage and loaded control feedthrough |
| [amp_022_fer_two_stage](cases/amp_022_fer_two_stage/README.md) | Complete two-stage Miller amplifier with physical bias mirror | 1.5 V, 20 uA, 10 pF; balanced AC and direct-follower recovery |
| [amp_029_two_stage_miller_comp](cases/amp_029_two_stage_miller_comp/README.md) | Differential two-stage Miller without CMFB | Fixed 0.7087 V load bias; source-paired differential response and disclosed common-mode sensitivity |
| [amp_001_5t](cases/amp_001_5t/README.md) | Five-transistor OTA plus bias mirror | 1.5 V, 20 uA reference, 10 pF, TT, 27 C |
| [buf_001_super_follower](cases/buf_001_super_follower/README.md) | Local feedback with internal physical MIM compensation | 0.55–0.65 V input, 5/10/20 pF, source/RC gain and step recovery |
| [sw_002_chopper_diff](cases/sw_002_chopper_diff/README.md) | Eight-MOS differential polarity commutation | Both input polarities and clock states, Ron, loaded switching and clock injection |
| [cmfb_004_output_switched_cap](cases/cmfb_004_output_switched_cap/README.md) | Four-MIM sampled common-mode sensing | Five conditions, sampled error, hold drift and supplied clock energy; driven inputs, not amplifier-loop stability |
| [drv_001_pam4_sige_dac](cases/drv_001_pam4_sige_dac/README.md) | Upstream 4 V broadband SiGe PAM4 driver | 4 V signoff point; native DRC/LVS, CC extraction and source-paired RF/tone score |
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
| [ldo_001_analoggym_basic](cases/ldo_001_analoggym_basic/README.md) | Folded/cascoded error amplifier with auxiliary pass-gate drive and physical 3:1 divider | 831 MOS, four MIM, sixteen poly; 0.225 V reference, 1.2/1.3 V supply, 200 ns load edges and 10/20 us zero-state ramps; faster-edge behavior is outside the scored stimulus |
| [vref_001_vgs](cases/vref_001_vgs/README.md) | Mixed LV/HV two-transistor reference | 1.0–1.5 V, −20–85 C typical-model samples, ±1 pA loading, zero-state ramp and sustained recovery; no precision-reference claim |
| [amp_027_fan_rrl_ota](cases/amp_027_fan_rrl_ota/README.md) | 16-MOS telescopic OTA with transistor DDA-CMFB | Preserved core; differential gain/step, output common mode and disturbance recovery |
| [amp_026_fan_chopper_ota](cases/amp_026_fan_chopper_ota/README.md) | 23-MOS two-stage OTA with static output chopper | Physical compensation, differential feedback step; extracted common-mode collapse disclosed and continuously scored |
| [ia_002_fan_chopper_simple](cases/ia_002_fan_chopper_simple/README.md) | Complete 39-MOS capacitive chopper IA | 5 kHz clocks, 100/200 Hz finite-window transfer, input impedance, residual and modulation observations |
| [ia_003_fan_chopper_pf](cases/ia_003_fan_chopper_pf/README.md) | 47-MOS capacitive IA retaining positive-feedback network | Same real-clock observation contract; positive-feedback switching and input impedance measured without a paper boost threshold |
| [amp_014_ramos_pfc](cases/amp_014_ramos_pfc/README.md) | Three-stage core with output feedforward and two retained compensation paths | 2583 expanded MOS; 1.5 V, 24 uA, balanced differential AC and 200 us follower response |
| [amp_011_peng_iac](cases/amp_011_peng_iac/README.md) | Cascoded bias and active auxiliary current compensation with physical R/C | 505 MOS; 1.5 V, 0.711568 uA, valid differential AC and finite-window oscillatory response |
| [amp_016_song_dacfc](cases/amp_016_song_dacfc/README.md) | Auxiliary input pair, active feedforward/feedback and two physical compensation capacitors | 472 MOS; 1.5 V, 5 uA, source/RC gain and finite-window response; no settled-operation claim |
| [amp_013_qu2017_azc](cases/amp_013_qu2017_azc/README.md) | Three-stage active compensation with retained R/C networks | 1.5 V, 1 uA, 10 pF; differential AC and finite-window follower ripple |
| [amp_021_yan_az](cases/amp_021_yan_az/README.md) | Cascoded input network and active compensation | 1.5 V, 10.981 uA, 10 pF; source/RC oscillatory follower observations |
| [amp_034_fan_chopper_cmfb](cases/amp_034_fan_chopper_cmfb/README.md) | Static-chopper two-stage core with upstream transistor output CMFB | 1.2 V; differential gain/step, output reference and common-mode kick/input-CM observations |
| [amp_035_fan_chopper_cmfb_dual](cases/amp_035_fan_chopper_cmfb_dual/README.md) | Independent flattened core with both upstream transistor CMFB loops | 1.2 V; both references, joint disturbance/quiet dynamics, preserved 50 MOhm sensing and 100 pF compensation |

The OTA is a conversion pilot related to the existing GF180 OTA family.
The buffer adds physical compensation and loaded local-feedback measurements;
the chopper adds differential commutation and driven-input clock feedthrough.
PDK and sizing variants do not automatically add topology coverage.

Materials retain PolyForm Noncommercial and applicable Apache/MIT/BSD component
terms in [LICENSE](LICENSE) and [NOTICE](NOTICE). The ferrosim component record
distinguishes the recorded author attribution and MIT label from an
original copyright notice that was not independently retrieved. The framework
MIT license does not replace these circuit/material terms.

Follow each case's reproduction commands and the shared
[tool setup](../../../docs/tools.md). Only the declared problem, physical
netlist, equivalent simulator representation and measurement deck enter a
standard solve. References, reader results, source records, licenses and host
configuration remain outside solver inputs. Retain collection LICENSE and
NOTICE with material distributions.

## Source screening exclusions

Internal ideal amplifier/readout macros and behavioral common-mode servos are
excluded from this collection's admission candidates. Replacing such macros
with an unrelated transistor circuit does not make the original source eligible.
Ordinary passive components, independent bias supplies and external measurement
apparatus are not functional amplifier macros. In particular, PAM4's bias-port
VCCS tails are explicitly external to the upstream physical HBT core.

The fixed upstream snapshot was checked across the 71 circuit directories containing DUTs,
including every available abstract and PDK netlist (310 source/metadata files).
Nine circuits contain internal functional macros and are excluded:

- [`amp_025_hsu_classab_ota`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_025_hsu_classab_ota/abstract/netlist.spice#L86): Ideal CMFB servo.
- [`amp_028_ideal_fully_diff`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_028_ideal_fully_diff/abstract/netlist.spice#L26): Ideal differential amplifier.
- [`amp_030_miller_cmfb_composite`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_030_miller_cmfb_composite/abstract/netlist.spice#L22): Composite with ideal CMFB servo.
- [`amp_031_srmc_core_cmfb`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/amp_031_srmc_core_cmfb/abstract/netlist.spice#L39): Two behavioral CMFB servos.
- [`cmfb_001_ideal_rsense_servo`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/cmfb_001_ideal_rsense_servo/abstract/netlist.spice#L36): Ideal common-mode error amplifier.
- [`ia_001_hsu_bandpass_classab`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_001_hsu_bandpass_classab/abstract/netlist.spice#L115): Bandpass core with ideal CMFB.
- [`ia_004_fan_chopper_rrl`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_004_fan_chopper_rrl/abstract/netlist.spice#L6): Ideal CMFB and RRL readout.
- [`ia_005_hsu_pga_ideal`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/ia_005_hsu_pga_ideal/abstract/netlist.spice#L54): Ideal PGA amplifier core.
- [`sup_003_rrl_sc_integrator`](https://github.com/MacAnalog/spicexplorer-release/blob/263d0322f8900dc331536fbbe6c0e804514fc454/analog-db/circuits/sup_003_rrl_sc_integrator/abstract/netlist.spice#L111): Ideal integrator readout.

The other 62 circuits contain no such internal macro in their available source
netlists; this screening is not layout qualification. All 62
currently qualified analog-db cases across IHP and GF180 pass this source screen;
their existing physical/electrical qualifications are unchanged.

Qu/Yan and the two Fan CMFB composites retain their own fixed bindings and all physical compensation. Their reference results distinguish valid finite-window observations from settled operation. The dual-CMFB source leaves its nominal operating point even without commanded disturbances; this behavior is disclosed, with both-loop transient and numerical-sensitivity checks, rather than replaced by an ideal servo.

[adc_001_inv1b](cases/adc_001_inv1b/README.md) is qualified as its actual fixed-size CMOS inverter/threshold core at 1.2 V. It adds validated DC crossing, loaded transition and driver/supply power observations; it does not claim sampling or complete ADC functionality.
