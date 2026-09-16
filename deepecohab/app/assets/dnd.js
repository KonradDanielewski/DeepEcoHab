/* Drag and drop for the plot builder.
 *
 * The browser owns nothing but the gesture: a drop reports {shelf, field, kind, from}
 * into the "dnd-event" store and Python reduces it into the builder state. A shelf that
 * cannot take the chip never calls preventDefault, so the drop simply does not happen
 * and the browser shows the no-drop cursor on top of our red outline.
 */

(function () {
	"use strict";

	var PALETTE = "__palette__";
	var dragged = null;

	function shelfAccepts(shelf, kind) {
		var accepts = shelf.getAttribute("data-accepts");
		if (!accepts) return true;
		return accepts.split(" ").indexOf(kind) !== -1;
	}

	function clearMarks() {
		document.querySelectorAll(".drop-ok, .drop-no").forEach(function (node) {
			node.classList.remove("drop-ok", "drop-no");
		});
	}

	document.addEventListener("dragstart", function (event) {
		var chip = event.target.closest ? event.target.closest("[data-field]") : null;
		if (!chip) return;

		dragged = {
			field: chip.getAttribute("data-field"),
			kind: chip.getAttribute("data-kind"),
			from: chip.getAttribute("data-from") || PALETTE,
		};

		event.dataTransfer.effectAllowed = "move";
		event.dataTransfer.setData("text/plain", JSON.stringify(dragged));
		chip.classList.add("dragging");
	});

	document.addEventListener("dragend", function (event) {
		var chip = event.target.closest ? event.target.closest("[data-field]") : null;
		if (chip) chip.classList.remove("dragging");
		dragged = null;
		clearMarks();
	});

	document.addEventListener("dragover", function (event) {
		var shelf = event.target.closest ? event.target.closest("[data-shelf]") : null;
		if (!shelf || !dragged) return;

		if (shelfAccepts(shelf, dragged.kind)) {
			event.preventDefault(); // the only thing that makes a drop possible
			event.dataTransfer.dropEffect = "move";
			shelf.classList.add("drop-ok");
		} else {
			shelf.classList.add("drop-no");
		}
	});

	document.addEventListener("dragleave", function (event) {
		var shelf = event.target.closest ? event.target.closest("[data-shelf]") : null;
		if (shelf && !shelf.contains(event.relatedTarget)) {
			shelf.classList.remove("drop-ok", "drop-no");
		}
	});

	document.addEventListener("drop", function (event) {
		var shelf = event.target.closest ? event.target.closest("[data-shelf]") : null;
		if (!shelf) return;

		event.preventDefault();
		clearMarks();

		var payload = dragged;
		if (!payload) {
			try {
				payload = JSON.parse(event.dataTransfer.getData("text/plain"));
			} catch (error) {
				return;
			}
		}

		var target = shelf.getAttribute("data-shelf");
		if (!shelfAccepts(shelf, payload.kind) || target === payload.from) return;

		window.dash_clientside.set_props("dnd-event", {
			data: {
				shelf: target,
				field: payload.field,
				kind: payload.kind,
				from: payload.from,
				at: Date.now(), // makes every drop a distinct value, repeats included
			},
		});

		dragged = null;
	});
})();
