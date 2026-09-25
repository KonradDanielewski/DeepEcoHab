"""Tests for the recording-page callbacks that moved into ``assets/clientside.js``.

Each one replaced a server callback, so the checks run the JS in node and compare it against
the Python it was ported from: the window marks against ``_window_marks``, the export
filename against the string ops the old callback did.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from dash import Dash

Dash(__name__, use_pages=True, pages_folder="")

from deepecohab.app.pages.recording import _window_marks  # noqa: E402

CLIENTSIDE_JS = Path(__file__).parent.parent / "deepecohab" / "app" / "assets" / "clientside.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

_PRELUDE = """
// The renderer defines these two; the asset file only adds its own namespace.
const PREVENT = {description: "Throw to prevent updating all Outputs."};
global.window = {
	dash_clientside: {PreventUpdate: PREVENT, no_update: {}, set_props: () => {}},
	addEventListener: () => {},
};
// The heatmap centring watches the page, which node does not have.
global.document = {body: {}};
global.MutationObserver = class { observe() {} };
eval(require("fs").readFileSync(process.argv[2], "utf8"));
const deh = window.dash_clientside.deh;
const wanted = JSON.parse(require("fs").readFileSync(process.argv[3], "utf8"));

const eq = (got, want, what) => {
	if (JSON.stringify(got) !== JSON.stringify(want)) {
		throw new Error(`${what}: ${JSON.stringify(got)} !== ${JSON.stringify(want)}`);
	}
};
const prevents = (fn, what) => {
	try { fn(); } catch (err) { if (err === PREVENT) return; throw err; }
	throw new Error(what + ": expected PreventUpdate");
};
const fire = (triggered_id, value) => {
	window.dash_clientside.callback_context = {
		triggered_id,
		triggered: [{value}],
	};
};
"""

_HARNESS = (
	_PRELUDE
	+ """
// --- fullscreen / openExport: the right figure and title, out of several ---------------
const ids = [{plot: "activity-bar"}, {plot: "ranking-line"}, {plot: "chasings-heatmap"}];
const figures = ids.map((id, i) => ({data: [{y: [i]}], layout: {}}));
// deliberately a different order, as Dash gives no ordering guarantee between two ALL states
const titleIds = [{plot: "chasings-heatmap"}, {plot: "activity-bar"}, {plot: "ranking-line"}];
const titles = ["Chasings heatmap", "Activity per position", "Social dominance ranking"];

fire({type: "card-fullscreen", plot: "ranking-line"}, 1);
eq(
	deh.fullscreen(null, figures, ids, titles, titleIds),
	[true, "Social dominance ranking", figures[1]],
	"fullscreen picks the clicked plot"
);

fire({type: "card-fullscreen", plot: "ranking-line"}, null);
prevents(() => deh.fullscreen(null, figures, ids, titles, titleIds), "a rebuild is not a click");

fire({type: "card-export", plot: "activity-bar"}, 1);
eq(
	deh.openExport(null, figures, ids, titles, titleIds, {recording: "Cohort 1 WT"}),
	[
		true,
		{figure: figures[0], title: "Activity per position"},
		wanted.filename,
	],
	"openExport carries the figure, title and filename"
);

fire({type: "card-export", plot: "activity-bar"}, 1);
eq(
	deh.openExport(null, figures, ids, titles, titleIds, null)[2],
	"recording__activity-bar",
	"openExport falls back when there is no recording context"
);

// --- switchTab: a querystring edit that keeps the other parameters, plus the rec-tab -----
// mirror plotRequest reads (rec-tabs itself is built into rec-body, too late to be an Input).
const NO_UPDATE = window.dash_clientside.no_update;
fire("rec-tabs", "social");
eq(
	deh.switchTab("social", "?project=abc&tab=overview"),
	["?project=abc&tab=social", "social"],
	"switchTab"
);
eq(
	deh.switchTab("social", "?project=abc"),
	["?project=abc&tab=social", "social"],
	"switchTab adds tab"
);
// The tab the body mounts with is already in the search; the mirror still has to be filled.
eq(deh.switchTab("social", "?tab=social"), [NO_UPDATE, "social"], "switchTab on the current tab");

// --- windowControl: bounds, marks and the reset on a granularity change ----------------
for (const [granularity, bound] of [["day", wanted.days], ["phase_count", wanted.phases]]) {
	fire("rec-granularity", granularity);
	const bounds = {days: wanted.days, phases: wanted.phases};
	const out = deh.windowControl(granularity, [2, 3], bounds, {color_by: "sex"});
	eq(out[0], 1, "window min");
	eq(out[1], bound, "window max");
	eq(out[2], wanted.marks[String(bound)], `marks for ${bound}`);
	eq(out[3], [1, bound], "a granularity change re-spans the window");
	eq(out[4], {color_by: "sex", granularity, window: [1, bound]}, "controls merged");
}

// the mark thinning turns over at 12, so compare the whole ported rule against Python
for (const bound of Object.keys(wanted.marks)) {
	fire("rec-granularity", "day");
	const out = deh.windowControl("day", [1, 1], {days: Number(bound), phases: 0}, null);
	eq(out[2], wanted.marks[bound], `marks for ${bound} days`);
}

fire("rec-window", [2, 3]);
eq(
	deh.windowControl("day", [2, 3], {days: wanted.days, phases: wanted.phases}, null)[3],
	[2, 3],
	"a drag keeps the dragged window"
);
prevents(() => deh.windowControl("day", [2, 3], null, null), "windowControl without a context");

// --- filterControls: a dict merge, plus the group-mean disable rule -------------------
// The slider hands over hour boundaries [6, 19]; the controls keep the bins 6..18.
eq(
	deh.filterControls([6, 19], null, "sex", true, {window: [1, 5]}),
	[{window: [1, 5], hours: [6, 18], phases: [], color_by: "sex", group_mean: true}, false],
	"filterControls merges into the controls it was given and enables group mean"
);
eq(
	deh.filterControls([6, 19], null, "animal_id", true, {window: [1, 5]}),
	[{window: [1, 5], hours: [6, 18], phases: [], color_by: "animal_id", group_mean: false}, true],
	"filterControls forces group mean off and disables the switch when colouring by animal"
);
eq(
	deh.filterControls([6, 19], null, "subject_name", true, {window: [1, 5]}),
	[
		{window: [1, 5], hours: [6, 18], phases: [], color_by: "subject_name", group_mean: false},
		true,
	],
	"filterControls disables group mean for subject_name too"
);

// --- toggleEvents: sets only the figures whose event items show the wrong way --------
const sets = [];
window.dash_clientside.set_props = (id, props) => sets.push([id, props]);
const withEvents = {
	data: [{y: [1]}],
	layout: {
		shapes: [{name: "event-span", visible: true}, {name: "other", visible: true}],
		annotations: [{name: "event-label", visible: true}, {name: "other", visible: true}],
	},
};
const noEvents = {data: [], layout: {shapes: [{name: "other"}]}};
const plots = ["a", "b", "c", "d"].map((plot) => ({plot}));
deh.toggleEvents(false, [withEvents, {}, null, noEvents], plots);
eq(sets.map(([id]) => id.plot), ["a"], "toggleEvents sets only the figure that has events");
const hidden = sets[0][1].figure;
eq(
	hidden.layout.shapes,
	[{name: "event-span", visible: false}, {name: "other", visible: true}],
	"toggleEvents hides only event-span shapes"
);
eq(
	hidden.layout.annotations,
	[{name: "event-label", visible: false}, {name: "other", visible: true}],
	"toggleEvents hides only event-label annotations"
);
sets.length = 0;
deh.toggleEvents(false, [hidden], [{plot: "a"}]);
eq(sets.length, 0, "a figure already hiding its events is left alone");
deh.toggleEvents(true, [hidden], [{plot: "a"}]);
eq(sets[0][1].figure.layout.shapes[0].visible, true, "toggleEvents shows event-span shapes again");
sets.length = 0;
deh.toggleEvents(true, [withEvents], [{plot: "a"}]);
eq(sets.length, 0, "a figure already showing its events is left alone");

// --- plotRequest: only the showing tab asks, and only for inputs it was not drawn with -
const NO = window.dash_clientside.no_update;
const metric = (value) => [{id: {plot: "bar", option: "metric"}, value}];
const full = {
	window: [1, 2],
	granularity: "day",
	hours: [0, 23],
	phases: ["light_phase", "dark_phase"],
	group_mean: false,
};
const context = {recording: "r", days: 2, phases: 4};
const request = (tab, stores, options = metric("time"), controls = full, badges = []) => {
	window.dash_clientside.callback_context = {
		inputs_list: [null, null, null, null, options],
		states_list: [
			Object.entries(stores).map(([plot, value]) => ({id: {type: "plot-req", plot}, value})),
			badges,
		],
	};
	sets.length = 0;
	deh.plotRequest(context, controls, tab, "dark");
	return Object.fromEntries(sets.map(([id, props]) => [id.plot, props.data]));
};
const uses = ["window", "granularity"];
const drawn = {
	tab: "activity",
	uses,
	context,
	controls: {window: [1, 2], granularity: "day"},
	theme: "dark",
	opts: {metric: "time"},
};
eq(
	request("activity", {
		bar: {tab: "activity", uses},
		line: {tab: "social", uses},
		pie: {tab: "activity", uses},
	}),
	{bar: drawn, pie: Object.assign({}, drawn, {opts: {}})},
	"only the showing tab's cards ask, each with its own options and only the controls it takes"
);
eq(request("activity", {bar: drawn}), {}, "the inputs a card was drawn with ask for nothing");
eq(
	request("activity", {bar: drawn}, metric("time"), {...full, hours: [2, 5], phases: []}),
	{},
	"a control the card ignores asks for nothing"
);
eq(
	request("activity", {bar: drawn}, metric("visits")).bar.opts,
	{metric: "visits"},
	"a changed card option asks again"
);

// --- plotRequest badges: shown while a control the card ignores is narrowed -----------
const badge = (control, value) => ({id: {type: "badge", plot: "bar", control}, value});
const shown = (controls, badges) => {
	request("activity", {}, [], controls, badges);
	return Object.fromEntries(sets.map(([id, props]) => [id.control, props.hidden]));
};
const all = ["window", "hours", "phases", "group_mean"].map((control) => badge(control, true));
eq(shown(full, all), {}, "every control at full extent leaves the badges hidden");
eq(
	shown({...full, window: [2, 2], hours: [0, 11], phases: ["dark_phase"], group_mean: true}, all),
	{window: false, hours: false, phases: false, group_mean: false},
	"each narrowed control shows its badge"
);
eq(
	shown(Object.assign({}, full, {granularity: "phase_count", window: [1, 4]}), all),
	{},
	"a window over every phase is the whole recording"
);
eq(
	shown(full, all.map((b) => Object.assign({}, b, {value: false}))),
	{window: true, hours: true, phases: true, group_mean: true},
	"a widened control hides its badge again"
);
sets.length = 0;
deh.plotRequest(null, null, "activity", "dark");
eq(sets.length, 0, "no recording, no request");

// --- colorBy: the cohort cards redraw for a new colour only ---------------------------
eq(deh.colorBy({color_by: "sex"}, "animal_id"), "sex", "colorBy passes a new colour on");
eq(
	deh.colorBy({color_by: "sex", hours: [2, 5]}, "sex") === NO,
	true,
	"colorBy ignores the other controls"
);

// --- clickEvent: a re-rendered button is not a click ----------------------------------
const chip = {type: "chip-x", shelf: "y", field: "day"};
fire(chip, null);
eq(deh.clickEvent() === NO, true, "a re-render passes nothing on");
fire(chip, 1);
eq(deh.clickEvent().id, chip, "a click passes its id on");

// --- builderKind: the palette redraws for a new plot type only ------------------------
eq(deh.builderKind({kind: "box"}, "line"), "box", "builderKind passes a new type on");
eq(
	deh.builderKind({kind: "box", channels: {}}, "box") === NO,
	true,
	"builderKind ignores other edits"
);

// --- pageScroll: an opened recording takes the builder link to its project -------------
global.history = {};
global.requestAnimationFrame = () => {};
document.getElementById = () => null;
const pages = ["/recording", "/builder"].map((index) => ({id: {index}}));
window.dash_clientside.callback_context = {outputs_list: [pages, pages]};
const links = (pathname, search, hrefs) => deh.pageScroll(pathname, search, hrefs)[1];
eq(
	links("/recording", "?project=b&recording=r", ["/recording", "/builder?project=a"]),
	["/recording?project=b&recording=r", "/builder?project=b"],
	"a recording from another project moves the builder"
);
eq(
	links("/builder", "?project=c", ["/recording?project=b&recording=r", "/builder?project=b"]),
	["/recording?project=b&recording=r", "/builder?project=c"],
	"the builder keeps its own pick"
);
eq(
	links("/recording", "?project=b&recording=s", ["/recording", "/builder?project=c"]),
	["/recording?project=b&recording=s", "/builder?project=c"],
	"another recording of the same project leaves the builder alone"
);

console.log("ok");
"""
)


def _run(tmp_path: Path, harness: str, wanted: dict) -> None:
	script, data = tmp_path / "harness.js", tmp_path / "wanted.json"
	script.write_text(harness, encoding="utf-8")
	data.write_text(json.dumps(wanted), encoding="utf-8")
	result = subprocess.run(
		["node", str(script), str(CLIENTSIDE_JS), str(data)],
		capture_output=True,
		text=True,
		encoding="utf-8",
	)
	assert result.returncode == 0, result.stderr
	assert result.stdout.strip() == "ok"


def test_recording_clientside_callbacks(tmp_path):
	days, phases = 5, 13  # one below the mark-thinning threshold, one just above
	wanted = {
		"days": days,
		"phases": phases,
		"marks": {str(bound): _window_marks(1, bound) for bound in (1, 5, 12, 13, 30, 31)},
		"filename": "cohort 1 wt__activity-bar".replace(" ", "-"),
	}
	_run(tmp_path, _HARNESS, wanted)


_FORMAT_HARNESS = (
	_PRELUDE
	+ """
const NO_UPDATE = window.dash_clientside.no_update;
const sets = [];
window.dash_clientside.set_props = (id, props) => sets.push([id, props]);
const ids = [{plot: "p"}];
const apply = (fig, fmt, choices = wanted.colors) => {
	sets.length = 0;
	deh.applyFormat({p: fmt}, [fig], ids, choices);
	return sets.length ? sets[0][1].figure : null;
};
const titles = (layout) => Object.fromEntries(
	Object.keys(layout).filter((key) => /^[xy]axis\\d*$/.test(key))
		.map((key) => [key, (layout[key].title || {}).text || ""])
);
const bar = ({coloraxis: c}) => [c.cauto, c.cmin, c.cmax, c.colorbar.title.text, c.colorscale];
// Flattened rather than compared whole: plotly.py writes autorangeoptions' two keys the
// other way round, and an unset bound it leaves out entirely.
const ranges = (layout) => Object.fromEntries(
	Object.keys(layout).filter((key) => /^[xy]axis\\d*$/.test(key)).map((key) => {
		const axis = layout[key], opts = axis.autorangeoptions || {};
		const bounds = [opts.minallowed ?? null, opts.maxallowed ?? null];
		return [key, [axis.autorange ?? null, axis.range ?? null, ...bounds]];
	})
);
const edit = (key, value, store, fig = wanted.figure, choices = wanted.colors) => {
	window.dash_clientside.callback_context = {
		triggered_id: {type: "rec-fmt", key},
		triggered: [{prop_id: JSON.stringify({key, type: "rec-fmt"}) + ".value", value}],
	};
	return deh.editFormat(null, null, "p", store, [fig], ids, choices);
};

// --- applyFormat draws what builder/figure.py apply_format draws ----------------------
const formatted = apply(wanted.figure, wanted.fmt);
eq(titles(formatted.layout), titles(wanted.expected.layout), "axis titles match apply_format");
eq(bar(formatted.layout), bar(wanted.expected.layout), "colour axis matches apply_format");
eq(ranges(formatted.layout), ranges(wanted.expected.layout), "axis ranges match apply_format");
eq(apply(formatted, wanted.fmt), null, "re-applying the same format sets nothing");

const cleared = apply(formatted, {});
eq(titles(cleared.layout), titles(wanted.figure.layout), "clearing restores the server's titles");
eq(bar(cleared.layout), bar(wanted.figure.layout), "clearing restores the server's colour axis");
eq(ranges(cleared.layout), ranges(wanted.figure.layout), "clearing restores the server's ranges");

// a plot that drew its own range gives it up while a bound holds, and takes it back after
const drawn = {data: [], layout: {xaxis: {title: {text: "Hour"}, range: [-0.5, 23.5]}}};
const bounded = apply(drawn, {xmin: {on: "Hour", value: 2}});
eq(
	ranges(bounded.layout).xaxis,
	[true, null, 2, null],
	"a bound hands the server's range back to autorange"
);
eq(apply(bounded, {}).layout.xaxis.range, [-0.5, 23.5], "clearing gives the server's range back");

eq(
	apply(wanted.figure, {xaxis: {on: "another title", value: "X"}}),
	null,
	"a lapsed override draws nothing"
);
eq(apply(wanted.figure, {}), null, "an unformatted figure is left alone");

const on = wanted.auto.colorbar;
const inverted = apply(wanted.figure, {cmin: {on, value: 5}, cmax: {on, value: 2}});
eq(bar(inverted.layout), bar(wanted.figure.layout), "an inverted range is not drawn");

const scaled = apply(wanted.figure, {colorscale: {on: "", value: "Viridis"}});
eq(
	scaled.layout.coloraxis.colorscale,
	wanted.colors.colorscale.Viridis,
	"the colour scale is swapped"
);

// the recording plots bold their titles with <b>, and an override keeps that weight
const bold = {
	data: [],
	layout: {xaxis: {title: {text: "<b>Time</b>"}}, yaxis: {title: {text: "<b>Rank</b>"}}},
};
eq(
	apply(bold, {yaxis: {on: "<b>Rank</b>", value: "Score"}}).layout.yaxis.title.text,
	"<b>Score</b>",
	"an override keeps the bold"
);

// --- editFormat binds each edit to the automatic text it replaced ---------------------
const store = edit("yaxis", "  Visits  ", null);
eq(
	store,
	{p: {yaxis: {on: wanted.auto.yaxis, value: "Visits"}}},
	"an edit binds to the automatic title"
);
eq(edit("yaxis", wanted.auto.yaxis, store), {}, "typing the automatic title back clears it");
eq(edit("yaxis", "Visits", store) === NO_UPDATE, true, "an unchanged value is no update");

const lapsed = {p: {xaxis: {on: "another title", value: "Old"}}};
eq(edit("xaxis", "", lapsed) === NO_UPDATE, true, "an empty field keeps a lapsed override");

const flagged = (key) => sets.find(([id]) => id.key === key)[1].error;
sets.length = 0;
edit("cmax", 0.5, {p: {cmin: {on, value: 1}}});
eq(flagged("cmax"), "Must be above min", "an inverted range is flagged on the form");
sets.length = 0;
edit("xmax", 0.5, {p: {xmin: {on: wanted.auto.xaxis, value: 1}}});
eq(flagged("xmax"), "Must be above min", "an inverted x range is flagged too");

// --- a palette swaps the colours the colorway declares, and only those -----------------
const A = "rgb(10, 20, 30)", B = "rgb(40, 50, 60)", EDGE = "rgb(1, 2, 3)";
const cats = {
	data: [
		{line: {color: A}, fillcolor: "rgba(10, 20, 30, 0.2)"},
		{marker: {color: [B, A]}, x: [1, 2]},
		{line: {color: EDGE}},
	],
	layout: {colorway: [A, B]},
};
const RED = "rgb(200, 0, 0)", GREEN = "rgb(0, 200, 0)";
const palettes = {palette: {Three: [RED, GREEN, "rgb(0, 0, 200)"], One: ["rgb(9, 9, 9)"]}};
const pick = (name) => ({palette: {on: "", value: name}});

const recoloured = apply(cats, pick("Three"), palettes);
eq(recoloured.data[0].line.color, RED, "a category colour is swapped by its place");
eq(recoloured.data[0].fillcolor, "rgba(200,0,0,0.2)", "its shade keeps the alpha");
eq(recoloured.data[1].marker.color, [GREEN, RED], "per-point colours are swapped too");
eq(recoloured.data[2].line.color, EDGE, "a colour outside the colorway is left alone");
eq(recoloured.layout.colorway, [RED, GREEN], "the colorway follows");
eq(apply(recoloured, pick("Three"), palettes), null, "re-applying the palette sets nothing");

const restored = apply(recoloured, {}, palettes);
eq(
	[restored.data[0].line.color, restored.data[1].marker.color, restored.layout.colorway],
	[A, [B, A], [A, B]],
	"clearing restores the server's colours"
);

eq(
	apply(cats, pick("One"), palettes).layout.colorway,
	[A, B],
	"a palette too short for the categories is not drawn"
);
sets.length = 0;
edit("palette", "One", null, cats, palettes);
eq(flagged("palette"), "1 colours for 2 categories", "and the form says why");

window.dash_clientside.callback_context = {
	triggered_id: {type: "card-format", plot: "p"},
	triggered: [{value: 1}],
	outputs_list: [null, null, null, [{id: {type: "rec-fmt", key: "palette"}}]],
};
eq(
	deh.openFormat(null, [cats], ids, ["P"], ids, {}, palettes)[6],
	[
		{value: "Three", label: "Three · 3", disabled: false},
		{value: "One", label: "One · 1", disabled: true},
	],
	"the palette menu disables the ones too short for this plot"
);

console.log("ok");
"""
)


_PATCH_HARNESS = """
global.window = {};
const {readFileSync} = require("fs");
const fakeStore = (hashes) => {
	const seen = [];
	const dispatch = (action) => (seen.push(action.type), action);
	return {seen, getState: () => ({layoutHashes: hashes}), dispatch};
};
const early = fakeStore({"0,props,children,1": {hash: 1}});
window.dash_stores = [early];
eval(readFileSync(process.argv[2], "utf8"));
const late = fakeStore({});
window.dash_stores.push(late);

const reset = (path) => ({type: "RESET_COMPONENT_STATE", payload: {itempath: path}});
early.dispatch(reset(["0", "props", "children", 2]));
early.dispatch(reset(["0", "props", "children"]));
early.dispatch({type: "ON_PROP_CHANGE", payload: {}});
late.dispatch(reset(["0"]));
const want = JSON.stringify([["RESET_COMPONENT_STATE", "ON_PROP_CHANGE"], []]);
const got = JSON.stringify([early.seen, late.seen]);
if (got !== want) throw new Error(got + " !== " + want);
console.log("ok");
"""


def test_renderer_patch_drops_only_resets_with_nothing_to_reset(tmp_path):
	patch = CLIENTSIDE_JS.with_name("renderer_patch.js")
	script = tmp_path / "patch.js"
	script.write_text(_PATCH_HARNESS, encoding="utf-8")
	result = subprocess.run(
		["node", str(script), str(patch)], capture_output=True, text=True, encoding="utf-8"
	)
	assert result.returncode == 0, result.stderr
	assert result.stdout.strip() == "ok"


def test_format_matches_builder(tmp_path):
	import plotly.express as px
	import plotly.graph_objects as go
	import polars as pl

	from deepecohab.app.builder import figure
	from deepecohab.plotting.theme import COLORSCALES, PALETTES

	frame = pl.DataFrame({"a": [1, 2, 3, 4], "b": [1, 2, 1, 2], "g": ["p", "q", "p", "q"]})
	# Faceted, so the x title sits on several axes and the y title on one.
	fig = px.density_heatmap(frame, x="a", y="b", facet_col="g")
	auto = figure.auto_titles(fig)
	fmt = {
		key: {"on": auto[figure.FORMAT_BINDS[key]], "value": value}
		for key, value in (
			("xaxis", "X"),
			("yaxis", "Y"),
			("colorbar", "N"),
			("xmin", 1),
			("xmax", 4),
			("ymin", 0.5),
			("cmin", 1),
			("cmax", 3),
			("colorscale", "Viridis"),
		)
	}
	expected = go.Figure(fig)
	figure.apply_format(expected, fmt)

	wanted = {
		"figure": json.loads(fig.to_json()),
		"expected": json.loads(expected.to_json()),
		"auto": auto,
		"fmt": fmt,
		"colors": {"colorscale": COLORSCALES, "palette": PALETTES},
	}
	_run(tmp_path, _FORMAT_HARNESS, wanted)


def test_format_constants_match_python():
	"""The clientside copies of the Format tables must not drift from the Python ones.

	:func:`test_format_matches_builder` pins the behaviour but reads the keys from Python,
	so a key added on one side only would still pass it.
	"""
	from deepecohab.app.builder import figure
	from deepecohab.app.pages.builder import _SELECTS, PALETTE

	source = CLIENTSIDE_JS.read_text(encoding="utf-8")
	binds_block = re.search(r"const _FORMAT_BINDS = \{(.*?)\};", source, re.S)
	selects_block = re.search(r"const _FORMAT_SELECTS = \[(.*?)\];", source)
	assert binds_block and selects_block

	binds = dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", binds_block.group(1)))
	# The cards draw no figure title of their own, so the JS binds every key but that one.
	assert binds == {key: on for key, on in figure.FORMAT_BINDS.items() if key != "title"}
	assert tuple(re.findall(r'"([^"]+)"', selects_block.group(1))) == _SELECTS

	dnd = CLIENTSIDE_JS.with_name("dnd.js").read_text(encoding="utf-8")
	assert re.search(r'var PALETTE = "([^"]+)"', dnd).group(1) == PALETTE
