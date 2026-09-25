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
FONT_SIZE = 13

#: House sequential scale for heatmaps, teal through gold, replacing plain Viridis.
_AURORA_STOPS: list[str] = [
	"rgba(22, 191, 168, 0.8)",  # teal
	"rgba(30, 155, 224, 0.8)",  # cyan-blue
	"rgba(58, 111, 232, 0.8)",  # blue
	"rgba(107, 83, 222, 0.8)",  # indigo
	"rgba(154, 76, 214, 0.8)",  # violet
	"rgba(197, 63, 192, 0.8)",  # magenta
	"rgba(232, 67, 147, 0.8)",  # pink
	"rgba(246, 92, 106, 0.8)",  # rose
	"rgba(250, 126, 78, 0.8)",  # orange-red
	"rgba(252, 160, 44, 0.8)",  # orange
	"rgba(255, 210, 63, 0.8)",  # gold
]
AURORA: list[list] = [
	[position, color]
	for position, color in zip(
		np.linspace(0, 1, len(_AURORA_STOPS)).tolist(), _AURORA_STOPS, strict=True
	)
]

_COLORSCALE = {"sequential": AURORA, "sequentialminus": "Plasma", "diverging": "curl"}

COLORBAR = {
	"thicknessmode": "fraction",
	"thickness": 0.03,
	"lenmode": "fraction",
	"len": 1,
	"y": 1,
	"yanchor": "top",
	"title": {"side": "right"},  # to fix font color not applied from theme token
}

COLORSCALES: dict[str, list] = {
	"Aurora": AURORA,
	**{
		name: px.colors.make_colorscale(getattr(px.colors.sequential, name))
		for name in ("Viridis", "Cividis", "Plasma", "Inferno", "Magma", "Greys", "Blues", "YlOrRd")
	},
}

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

CAGE_LOOKS: dict[str, list[tuple[str, str]]] = {
	"light": [
		("#ffffff", "#c9d2d2"),  # --surface, --line-strong
		("#eef1f1", "#c9d2d2"),  # --sunken, --line-strong
		("#e0f1f3", "#1a7f91"),  # --accent-soft, --accent
		("#e0eaf6", "#3f7cc4"),  # --k-dim at 16%
		("#d7dada", "#6f7c7b"),  # --ink-3 at 28%
		("#a3ccd3", "#1a7f91"),  # --accent at 40%
		("#b2cbe7", "#3f7cc4"),  # --k-dim at 40%
		("#b0b7b6", "#4a5857"),  # --ink-3 at 55%, --ink-2
	],
	"dark": [
		("#151c1c", "#344242"),
		("#1c2525", "#344242"),
		("#143238", "#45b5c8"),
		("#24323c", "#72a4e4"),
		("#323b3a", "#7b8988"),
		("#285961", "#45b5c8"),
		("#3a526c", "#72a4e4"),
		("#4d5857", "#a3b1b0"),
	],
}

#: Trace defaults every theme shares: a bare line is a smooth curve with no markers.
_DATA = {"scatter": [{"mode": "lines", "line": {"shape": "spline"}}]}


def _template(tokens: dict[str, str]) -> go.layout.Template:
	"""Build a card-surface template from one theme's tokens."""
	axis = {
		"gridcolor": "rgba(0,0,0,0)",  # tokens["grid"], decide whether to keep the grid or no
		"linecolor": tokens["axis"],
		"zerolinecolor": tokens["axis"],
		"tickcolor": tokens["axis"],
		"tickfont": {"color": tokens["ink2"]},
		"title": {"font": {"color": tokens["ink2"]}},
	}
	return go.layout.Template(
		data=_DATA,
		layout=go.Layout(
			paper_bgcolor="rgba(0,0,0,0)",
			plot_bgcolor="rgba(0,0,0,0)",
			font={"family": FONT, "size": FONT_SIZE, "color": tokens["ink"]},
			xaxis=axis,
			yaxis=axis,
			shapedefaults={"line": {"color": tokens["axis"]}},
			polar={
				"bgcolor": "rgba(0,0,0,0)",
				"angularaxis": {"gridcolor": tokens["grid"], "linecolor": tokens["axis"]},
				"radialaxis": {"gridcolor": "rgba(0,0,0,0)", "linecolor": tokens["axis"]},
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
		),
	)


DARK_THEME = _template(_TOKENS["dark"])
LIGHT_THEME = _template(_TOKENS["light"])

_PUBLICATION_AXIS = {
	"showgrid": False,
	"linecolor": "#000000",
	"linewidth": 1,
	"zerolinecolor": "#000000",
	"tickcolor": "#000000",
	"ticks": "outside",
	"tickfont": {"color": "#000000"},
	"title": {"font": {"color": "#000000"}},
}

PUBLICATION_THEME = go.layout.Template(
	data=_DATA,
	layout=go.Layout(
		paper_bgcolor="#ffffff",
		plot_bgcolor="#ffffff",
		font={"family": "Arial, sans-serif", "size": FONT_SIZE, "color": "#000000"},
		xaxis=_PUBLICATION_AXIS,
		yaxis=_PUBLICATION_AXIS,
		legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": "#000000"}},
		hoverlabel={"bgcolor": "#ffffff", "bordercolor": "#000000", "font": {"color": "#000000"}},
		shapedefaults={"line": {"color": "#000000"}},
		colorway=DEFAULT_COLORWAY,
		colorscale=_COLORSCALE,
		coloraxis={
			"colorbar": {
				"thicknessmode": "fraction",
				"thickness": 0.025,
				"lenmode": "fraction",
				"len": 1,
				"y": 1,
				"yanchor": "top",
				"title": {"side": "right", "font": {"color": "black"}},
			}
		},
	),
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
