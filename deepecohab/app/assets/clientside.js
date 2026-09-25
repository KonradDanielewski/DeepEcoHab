/* Callbacks that need no server work, as window.dash_clientside.deh.
 *
 * Python references each one as ClientsideFunction(namespace="deh", function_name=...).
 * Anything that reads a file, loads a project or builds a figure stays a server callback;
 * what lives here only rearranges state the browser already holds.
 */

(function () {
"use strict";

window.dash_clientside = window.dash_clientside || {};

/* The plot whose card button fired, out of the figures already held in the browser. */
function _pickPlot(figures, ids) {
	const dc = window.dash_clientside;
	const trigger = dc.callback_context.triggered[0];
	if (!trigger || !trigger.value) throw dc.PreventUpdate;
	const name = dc.callback_context.triggered_id.plot;
	const index = ids.findIndex((id) => id.plot === name);
	if (index < 0 || !figures[index]) throw dc.PreventUpdate;
	return {name: name, figure: figures[index]};
}

/* A card's <h3> text, which is PlotRegistry.spec(name).title as the page rendered it. */
function _plotTitle(name, titles, titleIds) {
	const index = titleIds.findIndex((id) => id.plot === name);
	return index < 0 ? name : titles[index];
}

/* Format: builder/figure.py apply_format for the recording cards, with the same lapse rule
 * - an override holds only while its element still carries the automatic text it was set
 * on. What the server drew is stashed in layout.meta.dehFormat when an override first lands,
 * so clearing one restores it; a rebuilt figure arrives without the stash and is read afresh.
 * A figure's category colours are the ones its layout.colorway declares (see
 * animals.collapse_legend); a palette swaps exactly those, so a weight-scaled edge keeps its. */
const _FORMAT_BINDS = {
	xaxis: "xaxis",
	xmin: "xaxis",
	xmax: "xaxis",
	yaxis: "yaxis",
	ymin: "yaxis",
	ymax: "yaxis",
	colorbar: "colorbar",
	cmin: "colorbar",
	cmax: "colorbar",
	colorscale: "coloraxis",
	palette: "colorway",
};
const _FORMAT_SELECTS = ["colorscale", "palette"];
const _FORMAT_BOUNDS = ["xmin", "xmax", "ymin", "ymax", "cmin", "cmax"];

function _titleText(title) {
	return (title && typeof title === "object" ? title.text : title) || "";
}

function _plain(text) {
	return (text || "").replace(/<[^>]*>/g, "");
}

/* ``text`` in the automatic title's weight: the recording plots bold theirs with <b>. */
function _like(auto, text) {
	return /^<b>.*<\/b>$/s.test(auto || "") ? "<b>" + text + "</b>" : text;
}

function _withTitle(owner, text) {
	const title = owner.title && typeof owner.title === "object" ? owner.title : {};
	return Object.assign({}, owner, {title: Object.assign({}, title, {text: text})});
}

/* The layout Format rewrites, as the server drew it. */
function _formatBase(layout) {
	const stash = (layout.meta || {}).dehFormat;
	if (stash) return stash;
	const axes = {};
	const ranges = {};
	Object.keys(layout)
		.filter((key) => /^[xy]axis\d*$/.test(key) && layout[key].visible !== false)
		.sort((a, b) => a.localeCompare(b, undefined, {numeric: true}))
		.forEach((key) => {
			axes[key] = _titleText(layout[key].title);
			ranges[key] = {range: layout[key].range ?? null, autorange: layout[key].autorange ?? null};
		});
	return {axes: axes, ranges: ranges, coloraxis: layout.coloraxis || null, colorway: layout.colorway || null};
}

/* Each element's automatic text: "" when drawn untitled, null when the figure has none. */
function _autoTitles(base) {
	const axis = (letter) => {
		const texts = Object.keys(base.axes).filter((key) => key[0] === letter).map((key) => base.axes[key]);
		return texts.length ? texts.find(Boolean) || "" : null;
	};
	const bar = base.coloraxis;
	return {
		xaxis: axis("x"),
		yaxis: axis("y"),
		colorbar: bar ? _titleText((bar.colorbar || {}).title) : null,
		coloraxis: bar ? "" : null,
		colorway: base.colorway ? "" : null,
	};
}

function _liveFormat(fmt, auto) {
	const live = {};
	Object.entries(fmt || {}).forEach(([key, entry]) => {
		const on = auto[_FORMAT_BINDS[key]];
		if (on !== null && entry.on === on) live[key] = entry.value;
	});
	return live;
}

/* The colour range the live bounds draw; null when there are none, "inverted" when unusable. */
function _colorRange(live, base) {
	if (live.cmin === undefined && live.cmax === undefined) return null;
	const axis = base.coloraxis || {};
	const cmin = live.cmin ?? axis.cmin;
	const cmax = live.cmax ?? axis.cmax;
	// With cauto off plotly fills a missing bound from the data.
	return cmin != null && cmax != null && cmin >= cmax ? "inverted" : {cauto: false, cmin: cmin, cmax: cmax};
}

/* The autorange bounds the live x/y overrides draw; null when there are none, "inverted"
 * when unusable. minallowed/maxallowed hold one bound while the data still sets the other. */
function _axisRange(live, letter) {
	const min = live[letter + "min"];
	const max = live[letter + "max"];
	if (min === undefined && max === undefined) return null;
	return min != null && max != null && min >= max ? "inverted" : {minallowed: min ?? null, maxallowed: max ?? null};
}

/* ``axis`` under ``bounds``, or handed back the range the server drew. A figure that drew
 * its own range has to hand it back to autorange for the bounds to count. */
function _withRange(axis, bounds, drawn) {
	const next = Object.assign({}, axis);
	delete next.autorangeoptions;
	delete next.autorange;
	delete next.range;
	if (bounds) Object.assign(next, {autorange: true, range: null, autorangeoptions: bounds});
	else Object.entries(drawn || {}).forEach(([key, value]) => value !== null && (next[key] = value));
	return JSON.stringify(next) === JSON.stringify(axis) ? axis : next;
}

/* "r,g,b" and the alpha of an rgb()/rgba() colour, or null for anything else. */
function _rgb(color) {
	const match = typeof color === "string" && /^rgba?\(([^)]*)\)$/.exec(color.trim());
	if (!match) return null;
	const parts = match[1].split(",").map(Number);
	return {key: parts.slice(0, 3).join(","), alpha: parts[3]};
}

/* The colorway the live palette draws; the server's while none is picked, or the pick has
 * too few colours to give every category its own. */
function _colorway(live, base, palettes) {
	const chosen = palettes[live.palette];
	return chosen && chosen.length >= base.colorway.length ? chosen.slice(0, base.colorway.length) : base.colorway;
}

/* ``data`` with each colour of ``from`` swapped for the one at its place in ``to``; an rgba()
 * shade of one keeps its alpha. */
function _recolor(data, from, to) {
	const place = new Map();
	from.forEach((color, i) => {
		const parsed = _rgb(color);
		if (parsed && _rgb(to[i])) place.set(parsed.key, to[i]);
	});
	const swap = (color) => {
		const parsed = _rgb(color);
		const target = parsed && place.get(parsed.key);
		if (!target) return color;
		return parsed.alpha === undefined ? target : `rgba(${_rgb(target).key},${parsed.alpha})`;
	};
	const walk = (node) => {
		const out = Object.assign({}, node);
		Object.entries(node).forEach(([key, value]) => {
			if (/color$/.test(key)) out[key] = Array.isArray(value) ? value.map(swap) : swap(value);
			else if (value && typeof value === "object" && !Array.isArray(value)) out[key] = walk(value);
		});
		return out;
	};
	return data.map(walk);
}

/* ``fig`` with ``fmt`` drawn on it, or null when that would change nothing. */
function _formatFigure(fig, fmt, choices) {
	if (!fig || !fig.layout) return null;
	const {colorscale: scales = {}, palette: palettes = {}} = choices || {};
	const stashed = Boolean((fig.layout.meta || {}).dehFormat);
	const base = _formatBase(fig.layout);
	const live = _liveFormat(fmt, _autoTitles(base));
	if (!stashed && !Object.keys(live).length) return null;

	const layout = Object.assign({}, fig.layout, {
		meta: Object.assign({}, fig.layout.meta, {dehFormat: base}),
	});
	["x", "y"].forEach((letter) => {
		const keys = Object.keys(base.axes).filter((key) => key[0] === letter);
		// Facets title only their outer axes; an untitled axis gets it on the first.
		const titled = keys.filter((key) => base.axes[key]);
		const targets = letter + "axis" in live ? (titled.length ? titled : keys.slice(0, 1)) : [];
		const range = _axisRange(live, letter);
		keys.forEach((key) => {
			const text = targets.includes(key) ? _like(base.axes[key], live[letter + "axis"]) : base.axes[key];
			const titledAxis = _titleText(layout[key].title) === text ? layout[key] : _withTitle(layout[key], text);
			layout[key] = _withRange(titledAxis, range === "inverted" ? null : range, (base.ranges || {})[key]);
		});
	});
	if (base.coloraxis) {
		const axis = Object.assign({}, base.coloraxis);
		if ("colorbar" in live) {
			const bar = axis.colorbar || {};
			axis.colorbar = _withTitle(bar, _like(_titleText(bar.title), live.colorbar));
		}
		if (scales[live.colorscale]) axis.colorscale = scales[live.colorscale];
		const range = _colorRange(live, base);
		if (range && range !== "inverted") Object.assign(axis, range);
		layout.coloraxis = axis;
	}
	// The data only changes along with the colorway, so comparing layouts still decides.
	let data = fig.data;
	if (base.colorway) {
		const colorway = _colorway(live, base, palettes);
		if (JSON.stringify(colorway) !== JSON.stringify(fig.layout.colorway)) {
			data = _recolor(fig.data || [], fig.layout.colorway || base.colorway, colorway);
			layout.colorway = colorway;
		}
	}
	return JSON.stringify(layout) === JSON.stringify(fig.layout) ? null : Object.assign({}, fig, {data, layout});
}

/* What the form flags: a colour max under the min, or a palette with too few colours. */
function _formErrors(fmt, layout, palettes) {
	const base = _formatBase(layout || {});
	const live = _liveFormat(fmt, _autoTitles(base));
	const chosen = (palettes || {})[live.palette];
	const needed = (base.colorway || []).length;
	const crossed = (range) => (range === "inverted" ? "Must be above min" : null);
	return {
		cmax: crossed(_colorRange(live, base)),
		xmax: crossed(_axisRange(live, "x")),
		ymax: crossed(_axisRange(live, "y")),
		palette: chosen && chosen.length < needed ? `${chosen.length} colours for ${needed} categories` : null,
	};
}

function _flagErrors(fmt, layout, palettes) {
	const dc = window.dash_clientside;
	Object.entries(_formErrors(fmt, layout, palettes)).forEach(([key, error]) =>
		dc.set_props({type: "rec-fmt", key: key}, {error: error})
	);
}

// The hours slider's band and label, repainted as the handles move - the twin of
// recording.py's _hours_band / _hours_text, which paint the first one server-side.
function _shade(phase, selected) {
	const token = phase === "dark_phase" ? "--tick-dark" : "--tick-light";
	return "color-mix(in srgb, var(" + token + ") " + (selected ? 100 : 22) + "%, transparent)";
}

function _hoursBand(context, phases) {
	const onsets = context.onsets || {};
	const start = context.start_from;
	const other = Object.keys(onsets).find((name) => name !== start);
	const on = (name) => (phases || []).indexOf(name) >= 0;
	if (!other) return _shade(start, on(start));

	const mins = (name) => Number(onsets[name].slice(0, 2)) * 60 + Number(onsets[name].slice(3, 5));
	const first = (((mins(other) - mins(start)) % 1440) + 1440) % 1440 / 60;
	// Boundary h sits at h / 24 of the track, so the split lands under the other onset's tick.
	const split = (100 * first) / 24;
	return (
		"linear-gradient(90deg, " + _shade(start, on(start)) + " 0 " + split + "%, " +
		_shade(other, on(other)) + " " + split + "% 100%)"
	);
}

// Whether a control is at its full extent, where a card that ignores it loses nothing; the
// keys are recording.py's _BADGES.
const _unfiltered = {
	window: (c, context) => c.window[0] === 1 && c.window[1] === (c.granularity === "day" ? context.days : context.phases),
	hours: (c) => c.hours[0] === 0 && c.hours[1] === 23,
	phases: (c) => c.phases.length === 2,
	group_mean: (c) => !c.group_mean,
};

/* Square heatmaps shrink their x axis to the cells and push them toward the colour bar
 * (plot_factory's constraintoward="right"), so a wide card leaves all its spare width left
 * of the matrix. Sliding the drawing back by half of it centres matrix and colour bar as
 * one; the figure title, placed on the whole container, is held where it was. */
function _centreSquare(gd) {
	const layout = gd._fullLayout;
	const xaxis = layout && layout.xaxis;
	const paper = gd.querySelector(".svg-container");
	if (!xaxis || !paper) return;
	const domain = xaxis._inputDomain;
	const square = xaxis.constrain === "domain" && xaxis.constraintoward === "right";
	const shift = square ? ((domain[1] - domain[0]) * layout._size.w - xaxis._length) / 2 : 0;
	const slide = (element, px) => element && (element.style.transform = shift > 0.5 ? `translateX(${px}px)` : "");
	slide(paper, -shift);
	slide(gd.querySelector(".g-gtitle"), shift);
}

new MutationObserver(() => {
	document.querySelectorAll(".js-plotly-plot").forEach((gd) => {
		if (gd._dehAfterplot || !gd.on) return;
		gd._dehAfterplot = true;
		gd.on("plotly_afterplot", () => _centreSquare(gd));
		_centreSquare(gd);
	});
}).observe(document.body, {childList: true, subtree: true});

/* The recording controls bar sticks under the header; once its head row has scrolled off
 * the top it tucks away behind the header (see .is-tucked), leaving a strip that hovering
 * pulls back down. No callback behind it: the class follows the scroll alone, and the bar
 * is looked up each time because switching recordings rebuilds it. */
let _tuckPending = false;
window.addEventListener("scroll", function () {
	if (_tuckPending) return;
	_tuckPending = true;
	requestAnimationFrame(function () {
		_tuckPending = false;
		const bar = document.querySelector(".deh-controls");
		const head = bar && bar.previousElementSibling;
		if (head) bar.classList.toggle("is-tucked", head.getBoundingClientRect().bottom < 0);
	});
}, {passive: true});

/* Downloads load into a hidden frame (DOWNLOAD_FRAME in components.py), which gives the page
 * no event when a file starts arriving. So each request carries a token the server hands
 * back as the deh-download cookie with the file (downloads._echo_download_token), and the
 * button that asked spins until it lands. The frame has room for one request at a time, so
 * a new download ends the previous spinner too. */
let _endDownload = () => {};

function _startDownload(button, setUrl, url) {
	_endDownload();
	const token = Math.random().toString(36).slice(2);
	url.searchParams.set("download_token", token);
	setUrl(url.href);
	button.classList.add("is-downloading");
	const timer = setInterval(() => {
		if (document.cookie.includes(`deh-download=${token}`)) _endDownload();
	}, 250);
	_endDownload = () => {
		clearInterval(timer);
		button.classList.remove("is-downloading");
		_endDownload = () => {};
	};
}

document.addEventListener("click", function (event) {
	const link = event.target.closest && event.target.closest('a[target="deh-download"]');
	if (!link) return;
	// A menu item closes its dropdown on click, so the spinner goes on the menu's trigger.
	const menu = link.closest('[role="menu"]');
	const trigger = menu && document.getElementById(menu.getAttribute("aria-labelledby"));
	_startDownload(trigger || link, (href) => (link.href = href), new URL(link.href));
}, true);

document.addEventListener("submit", function (event) {
	const form = event.target;
	if (form.target !== "deh-download") return;
	const button = event.submitter || form.querySelector('[type="submit"]');
	_startDownload(button, (action) => (form.action = action), new URL(form.action));
}, true);

/* A file never loads a page in the frame, so a page that does is the server refusing -
 * shown as a toast, since the frame itself is out of sight. Flask's abort() puts its
 * message in the <p> after <h1>. */
document.addEventListener("load", function (event) {
	const frame = event.target;
	if (frame.name !== "deh-download") return;
	_endDownload();
	const page = frame.contentDocument;
	if (!page || !page.body || !page.body.textContent.trim()) return;
	const detail = page.querySelector("h1 + p");
	window.dash_clientside.set_props("notifications", {sendNotifications: [{
		action: "show", message: `Download failed: ${detail ? detail.textContent : page.title}`,
		className: "deh-toast deh-toast-bad", withCloseButton: true, autoClose: 8000,
	}]});
}, true);


window.dash_clientside.deh = {
	/* --- shell ------------------------------------------------------------ */

	themeToggle: function () {
		const dark = document.documentElement.getAttribute("data-mantine-color-scheme") === "dark";
		return dark ? "light" : "dark";
	},

	applyTheme: function (theme) {
		const dc = window.dash_clientside;
		const resolved = theme || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
		return [theme || dc.no_update, resolved];
	},

	toggleNav: function (nClicks, collapsed) {
		return !collapsed;
	},

	shellNavbar: function (collapsed, mobileOpened) {
		const tips = window.dash_clientside.callback_context.outputs_list[2];
		return [
			{width: collapsed ? 64 : 232, breakpoint: "sm", collapsed: {mobile: !mobileOpened}},
			collapsed ? "nav-collapsed" : null,
			tips.map(() => !collapsed),
		];
	},

	// Each nav link keeps the last URL its page showed, so returning lands on the same
	// recording or project, and the window scroll is kept per page.
	pageScroll: function (pathname, search, hrefs) {
		const dc = window.dash_clientside;
		const [pages, links] = dc.callback_context.outputs_list;
		if (!dc.pageScroll) {
			dc.pageScroll = {};
			history.scrollRestoration = "manual";
			// Links scroll to the top before this callback runs, so the offset is recorded
			// as the page scrolls, and not once the URL has already moved on.
			window.addEventListener("scroll", () => {
				if (location.pathname === dc.page) dc.pageScroll[dc.page] = window.scrollY;
			});
		}
		if (dc.page !== pathname) {
			dc.page = pathname;
			const top = dc.pageScroll[pathname] || 0;
			// The page is still hidden until Dash applies the outputs, and a hidden page
			// is too short to scroll, so wait for it to show.
			const page = document.getElementById(JSON.stringify({index: pathname, type: "page"}));
			const restore = () => {
				if (dc.page !== pathname) return;
				if (page && page.hidden) return requestAnimationFrame(restore);
				window.scrollTo(0, top);
			};
			requestAnimationFrame(restore);
		}
		// Opening a recording from another project points the plot builder at that project;
		// moving between pages or recordings of the same one leaves the builder's pick alone.
		const project = pathname === "/recording" && new URLSearchParams(search).get("project");
		const follow = project && project !== dc.recordingProject;
		if (follow) dc.recordingProject = project;
		return [
			pages.map((page) => page.id.index !== pathname),
			links.map((link, i) => {
				if (link.id.index === pathname) return pathname + search;
				if (follow && link.id.index === "/builder") return "/builder?project=" + project;
				return hrefs[i];
			}),
		];
	},

	/* --- recording -------------------------------------------------------- */

	// The hours slider runs over hour boundaries; the controls keep the hour bins between them.
	filterControls: function (bounds, phases, colorBy, groupMean, controls, context) {
		const dc = window.dash_clientside;
		const disabled = colorBy === "animal_id" || colorBy === "subject_name";
		const merged = Object.assign({}, controls || {}, {
			hours: [bounds[0], bounds[1] - 1],
			phases: phases || [],
			color_by: colorBy,
			group_mean: Boolean(groupMean) && !disabled,
		});
		// set_props rather than Outputs: nothing else writes these, and the band is a
		// readout of the two sliders above it, not a control of its own.
		if (context && context.onsets) {
			const whole = bounds[0] === 0 && bounds[1] === 24;
			dc.set_props("rec-hours-band", {style: {background: _hoursBand(context, phases)}});
			dc.set_props("rec-hours-label", {
				children: "Hours " + bounds[0] + " → " + bounds[1],
			});
			dc.set_props("rec-hours-hint", {
				children: whole ? "whole day" : bounds[1] - bounds[0] + " of 24 h",
			});
		}
		return [merged, disabled];
	},

	// Only a figure whose event shapes/annotations show the wrong way is set, so the switch
	// redraws just those plots; one with no events, or not loaded yet, is left alone.
	toggleEvents: function (show, figures, ids) {
		const dc = window.dash_clientside;
		const isEvent = (item) => item.name === "event-span" || item.name === "event-label";
		const stale = (item) => isEvent(item) && (item.visible !== false) !== show;
		const toggle = (item) => (isEvent(item) ? Object.assign({}, item, {visible: show}) : item);
		(figures || []).forEach((fig, i) => {
			const layout = (fig && fig.layout) || {};
			const shapes = layout.shapes || [];
			const annotations = layout.annotations || [];
			if (!shapes.some(stale) && !annotations.some(stale)) return;
			const next = Object.assign({}, layout, {shapes: shapes.map(toggle), annotations: annotations.map(toggle)});
			dc.set_props(ids[i], {figure: Object.assign({}, fig, {layout: next})});
		});
	},

	// A card is rebuilt only while its tab shows, and only for inputs it was not already
	// drawn with: a hidden tab catches up when opened, and returning to one costs nothing.
	// Each store starts as {tab, uses}: the tab its card sits on and the controls its plot
	// takes, so a control it ignores never rebuilds it - it shows that control's badge instead.
	// One run serves every card and sets only the stores and badges that change: every callback
	// run and every write re-runs the renderer's per-component checks, so one callback per card
	// made each tab switch several times dearer.
	plotRequest: function (context, controls, tab, theme) {
		const dc = window.dash_clientside;
		if (!context || !controls) return;
		const opts = {};
		dc.callback_context.inputs_list[4].forEach((option) => {
			(opts[option.id.plot] = opts[option.id.plot] || {})[option.id.option] = option.value;
		});
		dc.callback_context.states_list[0].forEach((store) => {
			const previous = store.value || {};
			if (previous.tab !== tab) return;
			const used = {};
			(previous.uses || []).forEach((key) => (used[key] = controls[key]));
			const request = {tab: tab, uses: previous.uses, context: context, controls: used, theme: theme, opts: opts[store.id.plot] || {}};
			if (JSON.stringify(request) !== JSON.stringify(previous)) dc.set_props(store.id, {data: request});
		});
		(dc.callback_context.states_list[1] || []).forEach((badge) => {
			const hidden = _unfiltered[badge.id.control](controls, context);
			if (hidden !== badge.value) dc.set_props(badge.id, {hidden: hidden});
		});
	},

	// The cohort cards follow colour alone, so the other controls leave them be.
	colorBy: function (controls, current) {
		const next = (controls || {}).color_by || "animal_id";
		return next === current ? window.dash_clientside.no_update : next;
	},

	// Also the only writer of rec-tab, which plotRequest reads instead of rec-tabs itself:
	// this fires only when the tabs exist, so it stays a safe place to touch them.
	switchTab: function (tab, search) {
		const params = new URLSearchParams(search || "");
		if (params.get("tab") === tab) return [window.dash_clientside.no_update, tab];
		params.set("tab", tab);
		return ["?" + params.toString(), tab];
	},

	windowControl: function (granularity, window_, context, controls) {
		const dc = window.dash_clientside;
		if (!context) throw dc.PreventUpdate;
		const bound = granularity === "day" ? context.days : context.phases;
		const value = dc.callback_context.triggered_id === "rec-granularity" ? [1, bound] : window_;
		const step = bound > 12 ? 2 : 1;  // mirrors _window_marks
		const marks = [];
		for (let v = 1; v <= bound; v += 1) {
			if ((v - 1) % step === 0 || v === bound) marks.push({value: v, label: String(v)});
		}
		// set_props, like the hours readout: the label is a readout of the slider, not a control.
		dc.set_props("rec-window-label", {
			children: (granularity === "day" ? "Days " : "Phases ") + value[0] + " → " + value[1],
		});
		dc.set_props("rec-window-hint", {
			children: value[0] === 1 && value[1] === bound ? "all " + bound : value[1] - value[0] + 1 + " of " + bound,
		});
		const merged = Object.assign({}, controls || {}, {granularity: granularity, window: value});
		return [1, bound, marks, value, merged];
	},

	fullscreen: function (_clicks, figures, ids, titles, titleIds) {
		const picked = _pickPlot(figures, ids);
		return [true, _plotTitle(picked.name, titles, titleIds), picked.figure];
	},

	openExport: function (_clicks, figures, ids, titles, titleIds, context) {
		const picked = _pickPlot(figures, ids);
		const recording = (context || {}).recording || "recording";
		return [
			true,
			{figure: picked.figure, title: _plotTitle(picked.name, titles, titleIds)},
			(recording + "__" + picked.name).toLowerCase().split(" ").join("-"),
		];
	},

	openFormat: function (_clicks, figures, ids, titles, titleIds, formats, choices) {
		const dc = window.dash_clientside;
		const picked = _pickPlot(figures, ids);
		const layout = picked.figure.layout || {};
		const base = _formatBase(layout);
		const auto = _autoTitles(base);
		const fmt = (formats || {})[picked.name];
		const live = _liveFormat(fmt, auto);
		const keys = dc.callback_context.outputs_list[3].map((field) => field.id.key);
		const hint = (key) => {
			if (key in auto) return _plain(auto[key]) || (auto[key] === "" ? "No title" : "Not on this plot");
			if (_FORMAT_SELECTS.includes(key)) return "Default";
			return String((base.coloraxis || {})[key] ?? "Auto");
		};
		const palettes = (choices || {}).palette || {};
		const needed = (base.colorway || []).length;
		_flagErrors(fmt, layout, palettes);
		return [
			true,
			"Format · " + _plotTitle(picked.name, titles, titleIds),
			picked.name,
			keys.map((key) => live[key] ?? (_FORMAT_SELECTS.includes(key) ? null : "")),
			keys.map(hint),
			keys.map((key) => auto[_FORMAT_BINDS[key]] === null),
			Object.entries(palettes).map(([name, colors]) => ({
				value: name,
				label: `${name} · ${colors.length}`,
				disabled: colors.length < needed,
			})),
		];
	},

	// Only the fields that fired are touched, so an override that has lapsed - its element
	// shows other text now, and the form shows it empty - is kept for when that text returns.
	editFormat: function (_values, _reset, plot, formats, figures, ids, choices) {
		const dc = window.dash_clientside;
		const ctx = dc.callback_context;
		const index = ids.findIndex((id) => id.plot === plot);
		if (index < 0 || !figures[index]) throw dc.PreventUpdate;
		const layout = figures[index].layout || {};
		const auto = _autoTitles(_formatBase(layout));
		const next = Object.assign({}, formats);
		const fmt = Object.assign({}, next[plot]);

		if (ctx.triggered_id === "rec-fmt-reset") {
			if (!ctx.triggered[0].value) throw dc.PreventUpdate;
			ctx.inputs_list[0].forEach((field) =>
				dc.set_props(field.id, {value: _FORMAT_SELECTS.includes(field.id.key) ? null : ""})
			);
			Object.keys(fmt).forEach((key) => delete fmt[key]);
		} else {
			const live = _liveFormat(fmt, auto);
			ctx.triggered.forEach((trigger) => {
				const key = JSON.parse(trigger.prop_id.slice(0, trigger.prop_id.lastIndexOf("."))).key;
				let value = typeof trigger.value === "string" ? trigger.value.trim() : trigger.value;
				if (_FORMAT_BOUNDS.includes(key) && typeof value !== "number") value = null;
				if (value === "" || value === undefined || value === _plain(auto[key])) value = null;
				if (value === (live[key] ?? null)) return;
				if (value === null) delete fmt[key];
				else fmt[key] = {on: auto[_FORMAT_BINDS[key]], value: value};
			});
		}

		_flagErrors(fmt, layout, (choices || {}).palette);
		if (Object.keys(fmt).length) next[plot] = fmt;
		else delete next[plot];
		return JSON.stringify(next) === JSON.stringify(formats || {}) ? dc.no_update : next;
	},

	// The figures are Inputs, so an override is redrawn onto every figure the server rebuilds;
	// they are set rather than declared as outputs, which would close a loop Dash refuses, and
	// _formatFigure's null for "nothing changed" is what ends the echo of each set.
	applyFormat: function (formats, figures, ids, choices) {
		const dc = window.dash_clientside;
		(figures || []).forEach((fig, i) => {
			const next = _formatFigure(fig, (formats || {})[ids[i].plot], choices);
			if (next) dc.set_props(ids[i], {figure: next});
		});
	},

	/* --- shared ----------------------------------------------------------- */

	// The export preview is the figure kaleido will render, at its real pixel size, which
	// past ~113mm is wider than the dialog's preview column. Rather than re-fit it smaller
	// - the warnings beside it are measured at the real size - it keeps that size and is
	// scaled down to fit the stage, so the shape on screen is the shape on paper.
	fitPreview: function (figure) {
		const dc = window.dash_clientside;
		const stage = document.getElementById("export-stage");
		const w = figure && figure.layout && figure.layout.width;
		const h = figure && figure.layout && figure.layout.height;
		if (!stage || !w || !h || !stage.clientWidth) return dc.no_update;

		const scale = Math.min(1, stage.clientWidth / w, stage.clientHeight / h);
		return {
			width: w + "px",
			height: h + "px",
			transform: "translate(-50%, -50%) scale(" + scale + ")",
			transformOrigin: "center",
		};
	},


	// Buttons a callback re-renders fire their pattern-matched callbacks again with no click
	// behind them. Routed through here, only a real click reaches the server, as {id, at}
	// in a store; `at` makes a repeat click on the same button a new value.
	clickEvent: function () {
		const dc = window.dash_clientside;
		const trigger = dc.callback_context.triggered[0];
		if (!trigger || !trigger.value) return dc.no_update;
		return {id: dc.callback_context.triggered_id, at: Date.now()};
	},

	// Dash carries no SVG components, so the habitat map arrives as markup on a data attribute
	// and is painted in here. Repainting is idempotent and cheap: this fires on every context
	// change, and the Diagnostics panel stays mounted behind the other tabs. The second pass is
	// for the run where the new card has not committed to the DOM yet.
	paintHabitat: function () {
		const paint = () => document.querySelectorAll("[data-hab]").forEach((el) => {
			if (el.dataset.hab === el.dataset.habPainted) return;
			el.innerHTML = el.dataset.hab;
			el.dataset.habPainted = el.dataset.hab;
		});
		paint();
		requestAnimationFrame(paint);
	},

	// The header's counters jump to the tab that explains them, and to its card if one is named.
	// Written with set_props rather than an Output: the tab value already drives switchTab, and
	// a second writer of it turns the app's dependency graph circular. A re-rendered button
	// fires with no click behind it. The card lands just below the sticky control bar, measured
	// where it sticks, which would otherwise cover the card's header.
	tabJump: function () {
		const dc = window.dash_clientside;
		const trigger = dc.callback_context.triggered[0];
		if (!trigger || !trigger.value) return;
		const [tab, card] = {
			"rec-habitat-jump": ["diagnostics"],
			"rec-quality-jump": ["diagnostics"],
			"rec-mice-jump": ["overview", "cohort-card"],
		}[dc.callback_context.triggered_id] || [];
		if (!tab) return;
		dc.set_props("rec-tabs", {value: tab});
		if (card) {
			requestAnimationFrame(() => {
				const el = document.getElementById(card);
				const bar = document.querySelector(".deh-controls");
				if (!el || !bar) return;
				const below = parseFloat(getComputedStyle(bar).top) + bar.offsetHeight + 16;
				window.scrollTo({top: scrollY + el.getBoundingClientRect().top - below, behavior: "smooth"});
			});
		}
	},

	/* --- builder ---------------------------------------------------------- */

	// The palette's chips offer the plot type's shelves, so it redraws for a new type only.
	builderKind: function (state, current) {
		const kind = (state || {}).kind;
		return !kind || kind === current ? window.dash_clientside.no_update : kind;
	},

	/* --- projects --------------------------------------------------------- */

	// The selection lives in the browser: a tick only repaints checkboxes, so nothing here is
	// worth a round trip. The two halves pair up — clicks write the store, the store paints the
	// boxes — and a repaint echoes back as an Input, so selectRecordings ignores any trigger
	// that already agrees with the store. A repaint only ever runs after the store is written,
	// so the echo never reads a stale one.
	selectRecordings: function (_checks, _all, _clear, selection) {
		const dc = window.dash_clientside;
		const ctx = dc.callback_context;
		const trigger = ctx.triggered_id;
		if (trigger === "selection-clear") return selection.length ? [] : dc.no_update;
		if (!trigger) return dc.no_update;

		const key = (id) => JSON.stringify([id.project, id.index]);
		const value = ctx.triggered[0].value;
		const keys = new Set(selection.map((pair) => JSON.stringify(pair)));
		const boxes = ctx.inputs_list[0].filter((box) =>
			trigger.type === "select-all"
				? box.id.project === trigger.index
				: box.id.project === trigger.project && box.id.index === trigger.index
		);
		const ticked = boxes.length > 0 && boxes.every((box) => keys.has(key(box.id)));
		if (ticked === value) return dc.no_update;  // a repaint, not a click

		boxes.forEach((box) => keys[value ? "add" : "delete"](key(box.id)));
		const same = keys.size === selection.length && selection.every((pair) => keys.has(JSON.stringify(pair)));
		return same ? dc.no_update : [...keys].sort().map((pair) => JSON.parse(pair));
	},

	// Sets the boxes instead of outputting them: they are selectRecordings' inputs, so declared
	// outputs here would close a loop through the store that Dash refuses to register.
	paintSelection: function (selection) {
		const dc = window.dash_clientside;
		const key = (id) => JSON.stringify([id.project, id.index]);
		const [boxes, heads] = dc.callback_context.states_list;
		const keys = new Set((selection || []).map((pair) => JSON.stringify(pair)));
		const paint = (box, checked) => box.value === checked || dc.set_props(box.id, {checked});
		boxes.forEach((box) => paint(box, keys.has(key(box.id))));
		heads.forEach((head) => {
			const mine = boxes.filter((box) => box.id.project === head.id.index);
			paint(head, mine.length > 0 && mine.every((box) => keys.has(key(box.id))));
		});
	},

	resetProgress: function () {
		return null;
	},

	resetParams: function (_clicks, defaults) {
		return [
			defaults.minimum_time,
			defaults.minimum_time_alone,
			defaults.chasing_time_window,
		];
	},

	copyPath: function () {
		const dc = window.dash_clientside;
		const trigger = dc.callback_context.triggered[0];
		if (!trigger || !trigger.value) return dc.no_update;
		const toast = (kind, message) => dc.set_props("notifications", {sendNotifications: [{
			action: "show", message, className: `deh-toast deh-toast-${kind}`,
			withCloseButton: false, autoClose: 5200,
		}]});
		const path = dc.callback_context.triggered_id.index;
		(navigator.clipboard ? navigator.clipboard.writeText(path) : Promise.reject()).then(
			() => toast("info", "Path copied"),
			() => toast("warn", "The browser blocked clipboard access; select the path instead."),
		);
		return dc.no_update;
	},
};
})();
