# Isolated-body extraction control

These independently drawn geometries contain one GF180 3.3 V NMOS, its
output-connected isolated P-well contact, a deep-N-well supply contact and an
outer substrate ring. Ports are `vdd vout vss`. They are extraction controls,
not runnable benchmark cases or functional circuit witnesses. No upstream
layout or historical fixture was consumed. Geometry is MIT-licensed under the
repository license; process rules/resources retain their own licenses.

`deep-well.gds` isolates the P-well using DNWELL. `nwell-ring.gds` adds an explicit
surface N-well annulus without changing terminal connectivity. The GF180 layer
assignments and isolation geometry follow the pinned physical resource profile.
Native topology extraction must keep vout and vss as distinct conductor nets in
both controls; MOS channel and well-junction conduction is not an interconnect
resistor. This connectivity invariant is the oracle, not a resistance constant.

Magic 8.3.678's resistance substrate preparation fills space on the well plane
and can bridge the DNWELL-only isolation. The negative control ensures the
adapter rejects a new resistor-only path between those ports. The N-well ring
provides the positive counterpart. The regression invokes real Magic and the
native SPICE reader using the existing GF180 case's declared resource/settings.
It establishes fail-closed connectivity validation, not distributed substrate
accuracy, foundry signoff or transistor startup performance.
