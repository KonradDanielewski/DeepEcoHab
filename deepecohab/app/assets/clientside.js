window.dash_clientside = Object.assign({}, window.dash_clientside, {
    clientside: {
        handle_slider_mode: function (mode) {
            if (mode === 'days_range') {
                return [false, true, "sum", false, "dash-radio"];
            } else {
                return [true, false, "sum", true, "dash-radio switch-disabled"];
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
        },
        is_disabled: function (config_data) {
            if (!config_data) {
                return true;
            }
            if (typeof config_data === 'object') {
                return Object.keys(config_data).length === 0;
            }
            return false;
        },
        toggle_bool: function (n_clicks, is_open) {
            if (!n_clicks) {
                return is_open;
            }
            return !is_open;
        },
        check_config_exists: function (config) {
            if (!config) {
                return true;
            }
            if (Object.keys(config).length === 0) {
                return true;
            }
            return false;
        },
        enable_on_click: function (n_clicks) {
            if (n_clicks > 0) {
                return false;
            }
            return window.dash_clientside.no_update;
        },
        is_checked: function (is_checked) {
            return !is_checked;
        },
    }
});