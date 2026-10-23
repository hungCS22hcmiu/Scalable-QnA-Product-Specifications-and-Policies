# The memory scale, checked against the Activity Monitor graph — 2026-10-23

Counts and colours only. The author read the graph; the sensor was read with `sysctl -n kern.memorystatus_vm_pressure_level`.

| When | Sensor | Activity Monitor graph | `memory_pressure` free |
| :--- | :---: | :--- | :--- |
| during item 3.6's first gate run (53 readings) | 1 | green | 47 % (start of the run) |
| 2026-10-23, before this task's first run | 2 | **yellow** | 44 % |

So on this machine **1 = green and 2 = yellow**, as the SDK header says (`NORMAL 1`, `WARN 2`, `CRITICAL 4`). The sensor has never read 0 in any
recorded sample (`docs/super-plan.md:311`: "1 or 2 in every sample, never 0"). Green stays exactly `1` (`corpus_gate.GREEN_LEVEL`); a
reading of 0 would be new and would stop a run. Free memory alone does not decide the colour (44 % free was yellow here).
ADR-015 cites this table.
