from typing import Literal

import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio


def sample_palette(count: int, cmap: str = "Phase") -> list[str]:
	"""Sample ``count`` visually distinct colours from a colorscale.

	Args:
		count: how many colours are needed.
		cmap: any named plotly colorscale.

	Returns:
		Exactly ``count`` colours, empty when ``count`` is not positive.
	"""
	if count <= 0:
		return []

	# Drop the closing endpoint: Phase is cyclic, so both ends give the same colour.
	positions = np.linspace(0, 1, count + 1)[:-1]

	return px.colors.sample_colorscale(cmap, positions)


# Shared by both themes: Phase is mid-luminance, so it reads on either ground.
DEFAULT_COLORWAY: list[str] = sample_palette(12)

FONT = "Geist, Segoe UI, system-ui, sans-serif"

#: House sequential scale for heatmaps, teal through gold, replacing plain Viridis.
_AURORA_STOPS: list[str] = [
	"rgb(22, 191, 168)",  # teal
	"rgb(30, 155, 224)",  # cyan-blue
	"rgb(58, 111, 232)",  # blue
	"rgb(107, 83, 222)",  # indigo
	"rgb(154, 76, 214)",  # violet
	"rgb(197, 63, 192)",  # magenta
	"rgb(232, 67, 147)",  # pink
	"rgb(246, 92, 106)",  # rose
	"rgb(250, 126, 78)",  # orange-red
	"rgb(252, 160, 44)",  # orange
	"rgb(255, 210, 63)",  # gold
]
AURORA: list[list] = [
	[position, color]
	for position, color in zip(
		np.linspace(0, 1, len(_AURORA_STOPS)).tolist(), _AURORA_STOPS, strict=True
	)
]

#: Severity scale for miss-rate plots: the same good/warn/bad hues as the status badges
#: (app.css --good/--warn/--bad), so a "worse" colour on a plot means the same thing it
#: does everywhere else in the app.
SEVERITY: list[list] = [
	[0.0, "rgb(31, 116, 69)"],
	[0.5, "rgb(230, 176, 74)"],
	[1.0, "rgb(180, 35, 47)"],
]

_COLORSCALE = {"sequential": AURORA, "sequentialminus": "Plasma", "diverging": "curl"}

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
	},
	"light": {
		"ink": "#14201f",
		"ink2": "#4a5857",
		"grid": "#e7ecec",
		"axis": "#c9d2d2",
		"hover_bg": "#ffffff",
		"hover_border": "#dde3e3",
	},
}


def _template(t: dict[str, str]) -> go.layout.Template:
	"""Build a card-surface template from one theme's tokens."""
	axis = {
		"gridcolor": t["grid"],
		"linecolor": t["axis"],
		"zerolinecolor": t["axis"],
		"tickcolor": t["axis"],
		"tickfont": {"color": t["ink2"]},
		"title": {"font": {"color": t["ink2"]}},
	}
	return go.layout.Template(
		layout=go.Layout(
			paper_bgcolor="rgba(0,0,0,0)",
			plot_bgcolor="rgba(0,0,0,0)",
			font={"family": FONT, "size": 13, "color": t["ink"]},
			xaxis=axis,
			yaxis=axis,
			polar={
				"bgcolor": "rgba(0,0,0,0)",
				"angularaxis": {"gridcolor": t["grid"], "linecolor": t["axis"]},
				"radialaxis": {"gridcolor": t["grid"], "linecolor": t["axis"]},
			},
			legend={"bgcolor": "rgba(0,0,0,0)", "font": {"color": t["ink2"]}},
			hoverlabel={
				"bgcolor": t["hover_bg"],
				"bordercolor": t["hover_border"],
				"font": {"color": t["ink"]},
			},
			colorway=DEFAULT_COLORWAY,
			colorscale=_COLORSCALE,
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
		colorway=DEFAULT_COLORWAY,
		colorscale=_COLORSCALE,
	)
)

pio.templates["dark"] = DARK_THEME
pio.templates["light"] = LIGHT_THEME
pio.templates["publication"] = PUBLICATION_THEME


def set_default_theme(theme: Literal["dark", "light"] = "dark") -> None:
	"""Make one of the package themes plotly's default for this process.

	Args:
		theme: which registered template to select.
	"""
	pio.templates.default = theme
