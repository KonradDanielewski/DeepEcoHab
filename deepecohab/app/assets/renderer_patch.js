/* Backport of dash#3929 for Dash 4.2-4.4.1: skip the RESET_COMPONENT_STATE a component
 * dispatches on every fresh render when there is nothing under its path to reset.
 *
 * The reducer only deletes layoutHashes keys under the path, so a reset with none there
 * changes nothing - yet every dispatch re-runs each mounted component's selector. One per
 * newly mounted component made inserting N components cost about N x (mounted components):
 * expanding a 52-recording project took 30 s, the app's first paint 7 s.
 *
 * ponytail: patches renderer internals (window.dash_stores, the action type, layoutHashes);
 * delete this file once the installed Dash includes #3929.
 */

(function () {
	"use strict";

	function patch(store) {
		if (!store || store.__dehResetPatch) return;
		store.__dehResetPatch = true;
		var dispatch = store.dispatch;
		store.dispatch = function (action) {
			var itempath = action && action.type === "RESET_COMPONENT_STATE" && action.payload && action.payload.itempath;
			if (itempath) {
				var prefix = itempath.join(",");
				var hashes = store.getState().layoutHashes || {};
				var stale = Object.keys(hashes).some(function (key) {
					return key.startsWith(prefix);
				});
				if (!stale) return action;
			}
			return dispatch(action);
		};
	}

	var stores = (window.dash_stores = window.dash_stores || []);
	stores.forEach(patch);
	var push = stores.push;
	stores.push = function () {
		Array.prototype.forEach.call(arguments, patch);
		return push.apply(this, arguments);
	};
})();
