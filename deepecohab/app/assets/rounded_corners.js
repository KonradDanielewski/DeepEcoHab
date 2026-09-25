/* Rounded corners plotly cannot draw itself, redone after every redraw.
 *
 * Loaded by the app as a Dash asset and by figure export into kaleido's page (see
 * plotting.export), whose Plotly.toImage plots into a hidden graph div and serialises its
 * live SVG - so what this rounds on that div is what the exported file shows. On kaleido's
 * page it runs from <head>, before <body> exists, and with none of the app around it.
 */
(function () {
	"use strict";

	/* Plotly has no corner radius for boxes, so each redraw rewrites the IQR rectangle of
	 * every box path ("M x,y H|V .. H|V .. H|V .. Z", orientation-agnostic) with rounded
	 * corners to match barcornerradius. Median and whiskers are separate open subpaths and
	 * stay square; notched boxes don't match and are left alone. */
	const BOX_RADIUS = 6;
	const NUM = "(-?[\\d.]+(?:e[-+]?\\d+)?)";
	const RECT = new RegExp(`M${NUM},${NUM}([HV])${NUM}([HV])${NUM}([HV])${NUM}Z`);

	function roundRect(radius, _match, x, y, ...steps) {
		const corners = [[+x, +y]];
		for (let i = 0; i < 6; i += 2) {
			const [px, py] = corners[corners.length - 1];
			corners.push(steps[i] === "H" ? [+steps[i + 1], py] : [px, +steps[i + 1]]);
		}
		const [[x0, y0], , [x2, y2]] = corners;
		const r = Math.min(radius, Math.abs(x2 - x0) / 2, Math.abs(y2 - y0) / 2);
		const toward = ([ax, ay], [bx, by]) => {
			const len = Math.hypot(bx - ax, by - ay) || 1;
			return `${ax + ((bx - ax) * r) / len},${ay + ((by - ay) * r) / len}`;
		};
		return corners.map((corner, i) => {
			const next = corners[(i + 1) % 4];
			const prev = corners[(i + 3) % 4];
			return `${i ? "L" : "M"}${toward(corner, prev)}Q${corner.join(",")} ${toward(corner, next)}`;
		}).join("") + "Z";
	}

	function roundPath(path, radius) {
		const d = path.getAttribute("d");
		const rounded = d && d.replace(RECT, (...match) => roundRect(radius, ...match));
		if (rounded !== d) path.setAttribute("d", rounded);
	}

	function roundBoxes(gd) {
		gd.querySelectorAll("path.box").forEach((path) => roundPath(path, BOX_RADIUS));
	}

	/* A heatmap with gaps between its cells reads as tiles, so the tiles are rounded too.
	 * Plotly paints every cell into one raster image, so each redraw clips that image to a
	 * rounded rect per cell, placed where plotly paints it: the cell's edges, inset by half
	 * the gap. Event outlines drawn on the cells (the recording pulse's) are rounded one
	 * pixel wider, to stay concentric with the tile inside. */
	const TILE_RADIUS = 10;

	function roundTiles(gd) {
		const layout = gd._fullLayout;
		(gd.calcdata || []).forEach((cd) => {
			const {trace, node3, x, y} = cd[0];
			if (trace.type !== "heatmap" || !(trace.xgap || trace.ygap) || !node3) return;
			const group = node3.node();
			const image = group.querySelector("image");
			if (!image) return;

			const xaxis = layout["xaxis" + trace.xaxis.slice(1)];
			const yaxis = layout["yaxis" + trace.yaxis.slice(1)];
			const xs = x.map((value) => xaxis.c2p(value));
			const ys = y.map((value) => yaxis.c2p(value));
			const tiles = [];
			for (let i = 1; i < xs.length; i++) {
				for (let j = 1; j < ys.length; j++) {
					const width = Math.abs(xs[i] - xs[i - 1]) - trace.xgap;
					const height = Math.abs(ys[j] - ys[j - 1]) - trace.ygap;
					if (width <= 0 || height <= 0) continue;
					const left = Math.min(xs[i], xs[i - 1]) + Math.floor(trace.xgap / 2);
					const top = Math.min(ys[j], ys[j - 1]) + Math.floor(trace.ygap / 2);
					const r = Math.min(TILE_RADIUS, width / 2, height / 2);
					tiles.push(`<rect x="${left}" y="${top}" width="${width}" height="${height}" rx="${r}"/>`);
				}
			}
			const clip = group.querySelector("clipPath") ||
				group.appendChild(document.createElementNS("http://www.w3.org/2000/svg", "clipPath"));
			clip.id = `deh-tiles-${layout._uid}-${trace.uid}`;
			clip.innerHTML = tiles.join("");
			image.setAttribute("clip-path", `url(#${clip.id})`);

			layout.shapes.forEach((shape, index) => {
				if (shape.name !== "event-span" || shape.xref !== trace.xaxis || shape.yref !== trace.yaxis) return;
				gd.querySelectorAll(`.shapelayer path[data-index="${index}"]`)
					.forEach((path) => roundPath(path, TILE_RADIUS + 1));
			});
		});
	}

	function round(gd) {
		roundBoxes(gd);
		roundTiles(gd);
	}

	new MutationObserver(() => {
		document.querySelectorAll(".js-plotly-plot").forEach((gd) => {
			if (gd._dehRounded || !gd.on) return;
			gd._dehRounded = true;
			gd.on("plotly_afterplot", () => round(gd));
			round(gd);
		});
	}).observe(document, {childList: true, subtree: true});
})();
