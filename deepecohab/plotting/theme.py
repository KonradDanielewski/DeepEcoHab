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

DARK_THEME = go.layout.Template(
	layout=go.Layout(
		paper_bgcolor="#161f34",
		plot_bgcolor="#161f34",
		font={"color": "#e0e6f0"},
		xaxis={"gridcolor": "#2e3b53", "linecolor": "#4fc3f7"},
		yaxis={"gridcolor": "#2e3b53", "linecolor": "#4fc3f7"},
		legend={"bgcolor": "rgba(0,0,0,0)"},
		colorway=DEFAULT_COLORWAY,
		colorscale={
			"sequential": "Viridis",
			"sequentialminus": "Plasma",
			"diverging": "curl",
		},
	)
)

LIGHT_THEME = go.layout.Template(
	layout=go.Layout(
		paper_bgcolor="#ffffff",
		plot_bgcolor="#f7f8fa",
		font={"color": "#1c2333"},
		xaxis={"gridcolor": "#dde1e8", "linecolor": "#4a5568"},
		yaxis={"gridcolor": "#dde1e8", "linecolor": "#4a5568"},
		legend={"bgcolor": "rgba(0,0,0,0)"},
		colorway=DEFAULT_COLORWAY,
		colorscale={
			"sequential": "Viridis",
			"sequentialminus": "Plasma",
			"diverging": "curl",
		},
	)
)

pio.templates["dark"] = DARK_THEME
pio.templates["light"] = LIGHT_THEME


def set_default_theme(theme: Literal["dark", "light"] = "dark") -> None:
	"""Make one of the package themes plotly's default for this process.

	Args:
		theme: which registered template to select.
	"""
	pio.templates.default = theme
