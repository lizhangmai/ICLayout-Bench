# Maintained Analog Academy circuits

The [catalog](catalog.toml) indexes four maintained SG13G2 circuits. Each case
contains declared, ready-to-use inputs and a reference layout. The case README
reports measurements, reproduction commands, and qualification limitations.

| Case | Circuit role | Status |
| --- | --- | --- |
| [comparator](cases/comparator/README.md) | Clocked differential comparator | Qualified |
| [input_pair](cases/input_pair/README.md) | Differential input stage | Qualified |
| [output_stage](cases/output_stage/README.md) | Amplifier output stage | Qualified |
| [full_OTA](cases/full_OTA/README.md) | Complete operational transconductance amplifier | Qualified |

Prepare the PDK and tools using the [tools guide](../../../docs/tools.md#manual-tools),
then follow the selected case's reproduction commands. References remain outside
standard solver inputs. Source attribution is recorded in each case's `origin.url`.
The shared [LICENSE](LICENSE) is copied to `materials/LICENSE` during
materialization and reference export.
