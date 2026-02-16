window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        handle_slider_mode: function (mode) {
            if (mode === 'days_range') {
                return [false, true, false, "dash-radio"];
            } else {
                return [true, false, true, "dash-radio switch-disabled"];
            }
        },
        sync_select_all: function (selectAllChecked, currentSelection, options) {
            const triggered = dash_clientside.callback_context.triggered;
            if (!triggered.length || !options) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }

            const propId = triggered[0].prop_id;
            const allValues = options.map(opt => opt.value);

            if (propId.includes('select-all')) {
                return selectAllChecked ? [allValues, true] : [[], false];
            }

            if (propId.includes('main-checklist')) {
                const isAllSelected = allValues.length > 0 &&
                    allValues.every(val => currentSelection.includes(val));
                return [window.dash_clientside.no_update, isAllSelected];
            }

            return [window.dash_clientside.no_update, window.dash_clientside.no_update];
        },
        toggle_modal: function (n_clicks, is_open, graph_ids) {
            if (!n_clicks) {
                return [is_open, window.dash_clientside.no_update];
            }

            const new_is_open = !is_open;
            let options = [];

            if (new_is_open && graph_ids) {
                options = graph_ids.map(id => {
                    const rawName = id.name;

                    const formattedLabel = rawName
                        .split('-')
                        .map(part => part.charAt(0).toUpperCase() + part.slice(1))
                        .join(' ');

                    return { label: formattedLabel, value: rawName };
                });
            }

            return [new_is_open, options];
        }
    }
});