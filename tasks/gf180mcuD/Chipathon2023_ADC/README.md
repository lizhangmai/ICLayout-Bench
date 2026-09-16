# Chipathon2023_ADC GF180 Layout Case

This collection contains one executable, qualified GF180MCU D case with a passing reference layout. It uses nominal 3.3 V / 27 C typical models and candidate-derived RC.

| Case | Function | Coefficient |
| --- | --- | --- |
| [Dynamic Comparator](cases/comparator/README.md) | A clocked differential comparator with an input stage and a regenerative output stage, using the 15 MOS devices in the maintained source. | 6 |

See the [catalog](catalog.toml), the case's complete problem/results, and [GF180 resource preparation](../../../docs/tools.md#gf180). Standard solver inputs exclude reference layouts. [LICENSE](LICENSE) accompanies the collection and is outside solver inputs.
