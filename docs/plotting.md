# Plotting

DeepEcoHab draws its figures straight from an analysed recording. Every plot is an
interactive [Plotly](https://plotly.com/python/) figure, so it can be zoomed, hovered,
restyled and exported. Run the analysis first, as described in the
[antenna analysis guide](./tutorial_antenna.md).

## Draw a plot

```python
import deepecohab as deh

project = deh.Project.load("path/to/projects/tsc2")
recording = project["cohort1_2023_05_17"]

figure = deh.plot("activity-bar", recording)
figure.show()
```

Options are passed as keyword arguments:

```python
deh.plot("activity-bar", recording, metric="visits", agg="mean", phase_type=["dark_phase"])
```

To make several plots of one recording, build a plot context once. It keeps the tables it
has read in memory instead of loading them again for every figure:

```python
context = deh.PlotContext.from_recording(recording)

context.plot("chasings-heatmap", days_range=(2, 4))
context.plot("ranking-line", mode="stability")
```

Each plot reads specific analysis tables. If one has not been built, the plot raises a
`ValueError` naming it.

An option value outside its allowed choices raises a `ValueError` listing them.

## Common options

Most plots share these options; the [plot list](#available-plots) says which each one takes.

| option | values | default | effect |
|---|---|---|---|
| `granularity` | `"day"`, `"phase_count"` | `"day"` | whether the window, and any per-unit breakdown, counts experiment days or phase occurrences |
| `days_range` | `(first, last)` | the whole recording | the window to plot, inclusive, in units of `granularity` |
| `phase_type` | a list of `"light_phase"`, `"dark_phase"` | both | which phases to include |
| `agg` | `"sum"`, `"mean"` | `"sum"` | total the window, or average it; bar plots then show the spread across days or phases, and line plots a standard-error band |
| `color_by` | `"animal_id"` or a cohort attribute | `"animal_id"` | colour each animal by its tag, or by its group |
| `scope` | `"cages"`, `"tunnels"`, `"all"` | `"cages"` | which positions to include |
| `unit` | `"auto"`, `"seconds"`, `"minutes"`, `"hours"`, `"days"` | `"auto"` | the unit durations are shown in; `"auto"` picks the largest one the data reaches |

`days_range` and `phase_type` filter by the calendar columns described in
[the analysis tables](./tutorial_antenna.md#calendar-columns): day 1 hour 0 is the onset of
the `start_from` phase.

**Colour by group.** `color_by` accepts `animal_id` and any of
`subject_name`, `sex`, `genotype`, `treatment`, `mouse_line` and `genetic_background` that
takes more than one value in the cohort. An animal keeps its colour in every plot, whatever
the selection. To list the attributes available for a recording:

```python
deh.available_attributes(context)
```

**Scope.** Plots drawing one panel per position (`cage-preference-evolution`,
`time-per-cage-heatmap`, `sociability-heatmap`) accept only `"cages"` or `"tunnels"`, since
cage times run to hours and tunnel times to seconds and cannot share one colour scale.

**Events.** Plots with a time axis (`cage-preference-evolution`, `time-per-cage-heatmap`,
`activity-line`, `chasings-line`, `ranking-line`) shade the recording's
[event bouts](./tutorial_antenna.md#metadata).

## Available plots

To list them in code: `deh.PlotRegistry.list_available()`.

### Activity

| plot | shows | options |
|---|---|---|
| `activity-bar` | visits to each position, or time spent there, per animal | `metric` (`"time"`, `"visits"`), `days_range`, `granularity`, `phase_type`, `agg`, `color_by`, `unit` |
| `time-alone-bar` | time each animal spent with no other animal present, per position | `days_range`, `granularity`, `phase_type`, `agg`, `scope`, `color_by`, `unit` |
| `cage-preference` | how the cohort's time is distributed across positions | `days_range`, `granularity`, `phase_type`, `scope`, `unit` |
| `cage-preference-evolution` | time per animal in each cage or tunnel, across days or phases | `days_range`, `granularity`, `agg`, `scope`, `unit` |
| `time-per-cage-heatmap` | time per animal in each cage or tunnel, across the 24 hours of the experiment day | `days_range`, `granularity`, `agg`, `scope`, `unit` |
| `activity-line` | antenna reads per hour of the day: the circadian rhythm | `days_range`, `granularity`, `agg`, `color_by` |

### Social hierarchy

| plot | shows | options |
|---|---|---|
| `chasings-line` | chasings per hour of the day | `days_range`, `granularity`, `agg`, `color_by` |
| `chasings-heatmap` | chaser-versus-chased matrix; columns are chasers, rows are chased | `days_range`, `granularity`, `phase_type`, `agg` |
| `ranking-line` | each animal's ranking (`ordinal`) over time, or with `mode="stability"` its rank order in each day or phase | `mode` (`"intime"`, `"stability"`), `days_range`, `granularity`, `color_by` |
| `ranking-distribution-line` | the probability density of each animal's rating on the last day or phase of the window | `days_range`, `granularity`, `color_by` |
| `network-dominance` | directed network of chasings, with node size showing ranking | `layout` (`"spring"`, `"circular"`), `days_range`, `granularity`, `color_by` |
| `tube-test-heatmap` | winner-versus-loser matrix of tube-test outcomes; needs the [tube test](./tutorial_antenna.md#tube-test) saved first | `days_range`, `granularity`, `phase_type`, `agg` |

### Sociability

| plot | shows | options |
|---|---|---|
| `sociability-heatmap` | time together, or number of meetings, for every pair, one panel per cage or tunnel | `metric` (`"time_together"`, `"pairwise_encounters"`), `days_range`, `granularity`, `phase_type`, `agg`, `scope`, `unit` |
| `cohort-heatmap` | in-cohort sociability, or the proportion of time together, for every pair | `metric` (`"sociability"`, `"proportion_together"`), `days_range`, `granularity`, `phase_type`, `scope` |
| `social-stability` | each pair's typical proportion of time together against how steady it stays across days or phases | `days_range`, `granularity`, `phase_type`, `scope`, `color_by` |
| `network-sociability` | undirected network weighted by the proportion of time each pair spends together | `layout` (`"spring"`, `"circular"`), `days_range`, `granularity`, `scope`, `color_by` |

In `cohort-heatmap`, `scope` changes `proportion_together` only: `sociability` is always
measured in cages, against chance cage occupancy.

### Overview

| plot | shows | options |
|---|---|---|
| `metrics-polar-line` | every metric of the feature table on one polar chart, as z-scored rates | `days_range`, `granularity`, `phase_type`, `color_by` |

The z-scores are computed for display across the animals of the recording, so they compare
animals within it, not across recordings. Compare recordings with the rates in the
[project table](./tutorial_antenna.md#combine-recordings).

## Themes

Two themes are included. To use one for every figure in the session:

```python
import plotly.io as pio

pio.templates.default = "light"  # or "dark"
```

Without this, figures use Plotly's default. To theme a single figure:
`figure.update_layout(template="dark")`.

## Save a figure

```python
figure.write_html("activity.html")    # interactive, opens in any browser
figure.write_image("activity.png", scale=3)  # static image for publication
figure.write_json("activity.json")    # reopen later with plotly.io.read_json()
```
