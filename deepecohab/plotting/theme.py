import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio


def sample_palette(count: int, cmap: str = "Phase") -> list[str]:
	"""Sample ``count`` visually distinct colours from any named plotly colorscale.

	Returns exactly ``count`` colours, empty when ``count`` is not positive.
	"""
	if count <= 0:
		return []

	# Drop the closing endpoint: Phase is cyclic, so both ends give the same colour.
	positions = np.linspace(0, 1, count + 1)[:-1][::-1]

	return px.colors.sample_colorscale(cmap, positions)


# Shared by both themes: Phase is mid-luminance, so it reads on either ground.
DEFAULT_COLORWAY: list[str] = sample_palette(12)

FONT = "Geist, Segoe UI, system-ui, sans-serif"

#: House sequential scale for heatmaps, teal through gold, replacing plain Viridis.
_AURORA_STOPS: list[str] = [
	"rgba(22, 191, 168, 0.7)",  # teal
	"rgba(30, 155, 224, 0.7)",  # cyan-blue
	"rgba(58, 111, 232, 0.7)",  # blue
	"rgba(107, 83, 222, 0.7)",  # indigo
	"rgba(154, 76, 214, 0.7)",  # violet
	"rgba(197, 63, 192, 0.7)",  # magenta
	"rgba(232, 67, 147, 0.7)",  # pink
	"rgba(246, 92, 106, 0.7)",  # rose
	"rgba(250, 126, 78, 0.7)",  # orange-red
	"rgba(252, 160, 44, 0.7)",  # orange
	"rgba(255, 210, 63, 0.7)",  # gold
]
AURORA: list[list] = [
	[position, color]
	for position, color in zip(
		np.linspace(0, 1, len(_AURORA_STOPS)).tolist(), _AURORA_STOPS, strict=True
	)
]

_COLORSCALE = {"sequential": AURORA, "sequentialminus": "Plasma", "diverging": "curl"}

#: One colour bar shape for every heatmap in the app, whatever built it. Both dimensions
#: are fractions of the plot area rather than pixels, so the bar keeps its proportions
#: when a card resizes instead of reading fat on a small plot and thin on a large one;
#: it hangs from the top of the plot area, where the data starts.
COLORBAR = {
	"thicknessmode": "fraction",
	"thickness": 0.025,
	"lenmode": "fraction",
	"len": 1,
	"y": 1,
	"yanchor": "top",
	"title": {"side": "right"},
}

#: What a heatmap's colour scale can be switched to, house scale first. Plotly.js knows
#: only a few scales by name, so every one is spelled out as explicit stops.
COLORSCALES: dict[str, list] = {
	"Aurora": AURORA,
	**{
		name: px.colors.make_colorscale(getattr(px.colors.sequential, name))
		for name in ("Viridis", "Cividis", "Plasma", "Inferno", "Magma", "Greys", "Blues", "YlOrRd")
	},
}

#: What a plot's categories can be recoloured with, which replaces the figure's
#: ``colorway`` colour for colour. As rgb() so the browser can match a shaded rgba() too.
PALETTES: dict[str, list[str]] = {
	name: px.colors.convert_colors_to_same_type(getattr(px.colors.qualitative, name), "rgb")[0]
	for name in (
		"Plotly",
		"D3",
		"T10",
		"Set1",
		"Set2",
		"Dark2",
		"Safe",
		"Bold",
		"Vivid",
		"Dark24",
		"Alphabet",
	)
}

#: App design tokens the card surface shows through, so plots carry no background of
#: their own. Values come from the blueprint's "Plot theme" spec, not the app's --ink /
#: --grid CSS variables directly, since the hover label pair there differs from --surface.
_TOKENS: dict[str, dict[str, str]] = {
	"dark": {
		"ink": "#e6eeed",
		"ink2": "#a3b1b0",
		"grid": "#212b2b",
		"axis": "#374444",
		"hover_bg": "#1c2525",
		"hover_border": "#2c3838",
		"dark_phase": "#7d8fae",
		"light_phase": "#9b8347",
	},
	"light": {
		"ink": "#14201f",
		"ink2": "#4a5857",
		"grid": "#e7ecec",
		"axis": "#c9d2d2",
		"hover_bg": "#ffffff",
		"hover_border": "#dde3e3",
		"dark_phase": "#5b6b85",
		"light_phase": "#e2c27e",
	},
}

#: The phase band's two colours per theme, the same ``--tick-dark`` / ``--tick-light`` the
#: hours slider paints its band with. A shape carries a literal colour, so a figure built
#: for one theme has to be recoloured for the other - see :func:`apply`.
PHASE_BAND: dict[str, dict[str, str]] = {
	name: {phase: tokens[phase] for phase in ("dark_phase", "light_phase")}
	for name, tokens in _TOKENS.items()
}


def _template(tokens: dict[str, str]) -> go.layout.Template:
	"""Build a card-surface template from one theme's tokens."""
	axis = {
		"gridcolor": tokens["grid"],
		"linecolor": tokens["axis"],
		"zerolinecolor": tokens["axis"],
		"tickcolor": tokens["axis"],
		"tickfont": {"color": tokens["ink2"]},
		"title": {"font": {"color": tokens["ink2"]}},
	}
	return go.layout.Template(
		layout=go.Layout(
			paper_bgcolor="rgba(0,0,0,0)",
			plot_bgcolor="rgba(0,0,0,0)",
			font={"family": FONT, "size": 13, "color": tokens["ink"]},
			xaxis=axis,
			yaxis=axis,
			shapedefaults={"line": {"color": tokens["axis"]}},
			polar={
				"bgcolor": "rgba(0,0,0,0)",
				"angularaxis": {"gridcolor": tokens["grid"], "linecolor": tokens["axis"]},
				"radialaxis": {"gridcolor": tokens["grid"], "linecolor": tokens["axis"]},
			},
			legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": tokens["ink2"]}},
			hoverlabel={
				"bgcolor": tokens["hover_bg"],
				"bordercolor": tokens["hover_border"],
				"font": {"color": tokens["ink"]},
			},
			colorway=DEFAULT_COLORWAY,
			colorscale=_COLORSCALE,
			coloraxis={"colorbar": COLORBAR},
		)
	)


DARK_THEME = _template(_TOKENS["dark"])
LIGHT_THEME = _template(_TOKENS["light"])

#: For print or a journal figure: white ground, black axes, no grid. Unlike ``dark`` and
#: ``light`` it is never the process default - callers ask for it by name at export time.
PUBLICATION_THEME = go.layout.Template(
	layout=go.Layout(
		paper_bgcolor="#ffffff",
		plot_bgcolor="#ffffff",
		font={"family": "Arial, sans-serif", "size": 13, "color": "#000000"},
		xaxis={
			"showgrid": False,
			"linecolor": "#000000",
			"linewidth": 1,
			"zerolinecolor": "#000000",
			"tickcolor": "#000000",
			"ticks": "outside",
			"tickfont": {"color": "#000000"},
			"title": {"font": {"color": "#000000"}},
		},
		yaxis={
			"showgrid": False,
			"linecolor": "#000000",
			"linewidth": 1,
			"zerolinecolor": "#000000",
			"tickcolor": "#000000",
			"ticks": "outside",
			"tickfont": {"color": "#000000"},
			"title": {"font": {"color": "#000000"}},
		},
		legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#000000"}},
		hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#000000", "font": {"color": "#000000"}},
		shapedefaults={"line": {"color": "#000000"}},
		colorway=DEFAULT_COLORWAY,
		colorscale=_COLORSCALE,
		coloraxis={"colorbar": COLORBAR},
	)
)


def apply(figure: go.Figure, name: str) -> go.Figure:
	"""Put ``figure`` in the named theme, phase bands included.

	The template carries colour for everything a trace or an axis draws, but a shape holds a
	literal colour - so the phase band :func:`~deepecohab.plotting.plot_factory._phase_band`
	drew has to be repainted here. Anything but ``"dark"`` reads in the light colours,
	``"publication"`` among them.
	"""
	figure.update_layout(template=name or "light")

	for phase, color in PHASE_BAND.get(name, PHASE_BAND["light"]).items():
		figure.update_shapes(fillcolor=color, selector={"name": f"phase-band-{phase}"})

	return figure


pio.templates["dark"] = DARK_THEME
pio.templates["light"] = LIGHT_THEME
pio.templates["publication"] = PUBLICATION_THEME
