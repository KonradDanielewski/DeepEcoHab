/* Snapshot dropped files before yielding: drag entries are only readable during
 * the drop event. Dash's directory traversal awaits each entry before retrieving
 * the next one, which can lose the remaining files in an ordinary multi-file drop.
 * Folder drops and the file picker continue through Dash's normal handler.
 * TODO: Will be fixed in Dash 4.5.0
 */
(function () {
    "use strict";
    document.addEventListener("drop", function (event) {
        const target = event.target.closest && event.target.closest("#upload-files");
        if (!target || !event.dataTransfer) return;
        const items = Array.from(event.dataTransfer.items || []);
        const entries = items.map(function (item) {
            return item.webkitGetAsEntry ? item.webkitGetAsEntry() : null;
        });
        if (entries.some(function (entry) { return entry && entry.isDirectory; })) return;
        const files = Array.from(event.dataTransfer.files || []);
        if (!files.length) return;
        event.preventDefault();
        event.stopPropagation();
        target.classList.remove("is-over");
        Promise.all(files.map(function (file) {
            return new Promise(function (resolve, reject) {
                const reader = new FileReader();
                reader.onload = function () { resolve(reader.result); };
                reader.onerror = function () { reject(new Error("Could not read " + file.name)); };
                reader.readAsDataURL(file);
            });
        })).then(function (contents) {
            window.dash_clientside.set_props("upload-files", {
                contents: contents,
                filename: files.map(function (file) { return file.name; }),
                last_modified: files.map(function (file) { return file.lastModified / 1000; })
            });
        }).catch(function (error) {
            window.dash_clientside.set_props("upload-report", { children: error.message });
        });
    }, true);
})();
