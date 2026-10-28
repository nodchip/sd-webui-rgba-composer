(() => {
    const appRoot = () => gradioApp();

    function findInput(root) {
        return root?.matches?.("input, textarea") ? root : root?.querySelector?.("input, textarea");
    }

    function setComponentValue(root, value) {
        const input = findInput(root);
        if (!input) return false;
        input.value = value;
        updateInput(input);
        return true;
    }

    function componentButton(root) {
        if (!root) return null;
        return root.matches?.("button") ? root : root.querySelector("button");
    }

    function sendLayerAction(action) {
        const app = appRoot();
        const actionRoot = app.getElementById("rgba_composer_action");
        const button = componentButton(app.getElementById("rgba_composer_action_button"));
        if (!setComponentValue(actionRoot, JSON.stringify(action)) || !button) return;
        requestAnimationFrame(() => button.click());
    }

    function selectedCard() {
        return appRoot().querySelector("#rgba_composer_layer_list .rgba-composer-layer.selected");
    }

    function compositorIsVisible() {
        const tab = appRoot().getElementById("tab_rgba_composer");
        return !!tab && tab.offsetParent !== null;
    }

    function clearDropMarkers(root) {
        root.querySelectorAll(".drop-before, .drop-after").forEach((card) => {
            card.classList.remove("drop-before", "drop-after");
        });
    }

    function setupLayerList() {
        const root = appRoot().getElementById("rgba_composer_layer_list");
        if (!root || root.dataset.rgbaComposerBound === "true") return;
        root.dataset.rgbaComposerBound = "true";

        root.addEventListener("click", (event) => {
            const actionButton = event.target.closest("button[data-action]");
            if (actionButton) {
                event.preventDefault();
                event.stopPropagation();
                const type = actionButton.dataset.action;
                if (type === "clear" && !window.confirm("RGBA Composerの全レイヤーを削除しますか？")) return;
                sendLayerAction({ type, layer_id: actionButton.dataset.layerId || "" });
                return;
            }

            const card = event.target.closest(".rgba-composer-layer");
            if (card && !event.target.closest("input")) {
                sendLayerAction({ type: "select", layer_id: card.dataset.layerId });
            }
        });

        root.addEventListener("change", (event) => {
            if (event.target.matches(".rgba-composer-name")) {
                sendLayerAction({
                    type: "rename",
                    layer_id: event.target.dataset.layerId,
                    value: event.target.value,
                });
            } else if (event.target.matches(".rgba-composer-opacity")) {
                sendLayerAction({
                    type: "opacity",
                    layer_id: event.target.dataset.layerId,
                    value: event.target.value,
                });
            }
        });

        root.addEventListener("input", (event) => {
            if (!event.target.matches(".rgba-composer-opacity")) return;
            const meta = event.target.closest(".rgba-composer-layer")?.querySelector(".rgba-composer-meta span:last-child");
            if (meta) meta.textContent = `${event.target.value}%`;
        });

        let draggedId = null;
        root.addEventListener("dragstart", (event) => {
            const card = event.target.closest(".rgba-composer-layer");
            if (!card || !event.target.closest(".rgba-composer-drag")) {
                event.preventDefault();
                return;
            }
            draggedId = card.dataset.layerId;
            card.classList.add("dragging");
            event.dataTransfer.effectAllowed = "move";
            event.dataTransfer.setData("text/plain", draggedId);
        });

        root.addEventListener("dragover", (event) => {
            const card = event.target.closest(".rgba-composer-layer");
            if (!draggedId || !card || card.dataset.layerId === draggedId) return;
            event.preventDefault();
            clearDropMarkers(root);
            const rect = card.getBoundingClientRect();
            card.classList.add(event.clientY < rect.top + rect.height / 2 ? "drop-before" : "drop-after");
        });

        root.addEventListener("drop", (event) => {
            const target = event.target.closest(".rgba-composer-layer");
            if (!draggedId || !target || target.dataset.layerId === draggedId) return;
            event.preventDefault();

            const cards = Array.from(root.querySelectorAll(".rgba-composer-layer"));
            const order = cards.map((card) => card.dataset.layerId).filter((id) => id !== draggedId);
            let index = order.indexOf(target.dataset.layerId);
            if (target.classList.contains("drop-after")) index += 1;
            order.splice(Math.max(0, index), 0, draggedId);
            clearDropMarkers(root);
            sendLayerAction({ type: "reorder", layer_id: draggedId, order });
        });

        root.addEventListener("dragend", () => {
            root.querySelectorAll(".dragging").forEach((card) => card.classList.remove("dragging"));
            clearDropMarkers(root);
            draggedId = null;
        });
    }

    function setupUndoExpiry() {
        const undo = appRoot().querySelector("#rgba_composer_layer_list .rgba-composer-undo");
        if (!undo || undo.dataset.timerSet === "true") return;
        undo.dataset.timerSet = "true";
        const delay = Math.max(0, Number(undo.dataset.expiresAt) - Date.now());
        window.setTimeout(() => undo.remove(), delay);
    }

    function setupKeyboard() {
        if (window.rgbaComposerKeyboardBound) return;
        window.rgbaComposerKeyboardBound = true;
        document.addEventListener("keydown", (event) => {
            if (!compositorIsVisible()) return;
            if (event.target.matches("input, textarea, select, [contenteditable='true']")) return;
            const card = selectedCard();
            if (!card) return;

            let type = null;
            if (event.key === "Delete") type = "delete";
            if (event.altKey && event.key === "ArrowUp") type = "up";
            if (event.altKey && event.key === "ArrowDown") type = "down";
            if (!type) return;

            event.preventDefault();
            sendLayerAction({ type, layer_id: card.dataset.layerId });
        });
    }

    function waitForElement(selector, timeoutMs = 10000) {
        return new Promise((resolve, reject) => {
            const current = appRoot().querySelector(selector);
            if (current) {
                resolve(current);
                return;
            }
            const observer = new MutationObserver(() => {
                const element = appRoot().querySelector(selector);
                if (!element) return;
                observer.disconnect();
                resolve(element);
            });
            observer.observe(appRoot(), { childList: true, subtree: true });
            window.setTimeout(() => {
                observer.disconnect();
                reject(new Error(`Timed out waiting for ${selector}`));
            }, timeoutMs);
        });
    }

    async function clearGradioImage(element) {
        for (const button of element.querySelectorAll("button")) {
            const label = button.getAttribute("aria-label") || "";
            if (label && !label.includes("Edit") && !label.includes("Éditer")) {
                button.click();
                await new Promise((resolve) => window.setTimeout(resolve, 50));
                return;
            }
        }
    }

    async function setGradioImage(element, blob, filename) {
        await clearGradioImage(element);
        const input = element.querySelector("input[type='file']");
        if (!input) throw new Error("File input not found");
        const file = new File([blob], filename, { type: "image/png" });
        const transfer = new DataTransfer();
        transfer.items.add(file);
        input.value = "";
        input.files = transfer.files;
        input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
    }

    function imageElementToPngBlob(image, background = null) {
        return new Promise((resolve, reject) => {
            const render = () => {
                const width = image.naturalWidth || image.width;
                const height = image.naturalHeight || image.height;
                if (!width || !height) {
                    reject(new Error("Image has no dimensions"));
                    return;
                }
                const canvas = document.createElement("canvas");
                canvas.width = width;
                canvas.height = height;
                const context = canvas.getContext("2d");
                if (background) {
                    context.fillStyle = background;
                    context.fillRect(0, 0, width, height);
                } else {
                    context.clearRect(0, 0, width, height);
                }
                context.drawImage(image, 0, 0, width, height);
                canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error("PNG encoding failed")), "image/png");
            };
            if (image.complete && image.naturalWidth) render();
            else {
                image.addEventListener("load", render, { once: true });
                image.addEventListener("error", () => reject(new Error("Image loading failed")), { once: true });
            }
        });
    }

    function selectedGalleryImage(galleryId) {
        const gallery = appRoot().getElementById(galleryId);
        if (!gallery) return null;
        return gallery.querySelector(".thumbnail-item.selected img") ||
            gallery.querySelector(".preview img") ||
            Array.from(gallery.querySelectorAll("img")).find((image) => image.offsetParent !== null) ||
            gallery.querySelector("img");
    }

    function switchToComposer() {
        const app = appRoot();
        const button = app.querySelector('button[aria-controls="tab_rgba_composer"]') ||
            app.getElementById("tab_rgba_composer-button") ||
            Array.from(app.querySelectorAll("#tabs button")).find((item) => item.textContent.trim() === "RGBA Composer");
        button?.click();
    }

    async function sendImageToComposer(image, source) {
        if (!image) {
            window.alert(`${source}に転送できる画像がありません。`);
            return;
        }
        try {
            const blob = await imageElementToPngBlob(image);
            switchToComposer();
            const inbox = await waitForElement("#rgba_composer_transfer_inbox");
            setComponentValue(appRoot().getElementById("rgba_composer_transfer_source"), source);
            await setGradioImage(inbox, blob, `${source.toLowerCase().replaceAll(" ", "-")}-output.png`);
        } catch (error) {
            console.error("RGBA Composer transfer failed", error);
            window.alert(`RGBA Composerへの転送に失敗しました: ${error.message}`);
        }
    }

    function addSendButton(container, key, title, handler) {
        if (!container || container.querySelector(`[data-rgba-composer-source="${key}"]`)) return;
        const button = document.createElement("button");
        const referenceButton = container.querySelector("button.gradio-button.tool") || container.querySelector("button");
        button.type = "button";
        button.className = referenceButton?.className || "lg secondary gradio-button tool";
        button.classList.add("rgba-composer-send-button");
        button.dataset.rgbaComposerSource = key;
        button.title = title;
        button.setAttribute("aria-label", title);
        button.textContent = "🧩";
        button.addEventListener("click", handler);
        container.appendChild(button);
    }

    function injectSourceButtons() {
        const app = appRoot();
        addSendButton(
            app.getElementById("image_buttons_img2img"),
            "img2img",
            "Send selected img2img output to RGBA Composer.",
            () => sendImageToComposer(selectedGalleryImage("img2img_gallery"), "img2img"),
        );
        addSendButton(
            app.getElementById("image_buttons_extras"),
            "extras",
            "Send selected Extras output to RGBA Composer.",
            () => sendImageToComposer(selectedGalleryImage("extras_gallery"), "Extras"),
        );

        const cleanerAnchor = app.getElementById("send_ia_cleaner_out_image_to_extras");
        const cleanerRow = cleanerAnchor?.closest(".gradio-row") || cleanerAnchor?.parentElement;
        addSendButton(
            cleanerRow,
            "cleaner",
            "Send selected Cleaner output to RGBA Composer.",
            () => sendImageToComposer(selectedGalleryImage("ia_cleaner_out_image"), "Cleaner"),
        );
    }

    window.rgbaComposerSendOutputToInpaintAnything = async function (matteColor) {
        const output = appRoot().querySelector("#rgba_composer_output img");
        if (!output) {
            window.alert("RGBA Composerに出力画像がありません。");
            return [];
        }
        try {
            const blob = await imageElementToPngBlob(output, matteColor || "#000000");
            if (typeof switch_to_inpaint_anything === "function") {
                switch_to_inpaint_anything();
            } else {
                const app = appRoot();
                const button = app.querySelector('button[aria-controls="tab_inpaint_anything"]') ||
                    app.getElementById("tab_inpaint_anything-button") ||
                    Array.from(app.querySelectorAll("#tabs button")).find((item) => item.textContent.trim() === "Inpaint Anything");
                button?.click();
            }
            const destination = await waitForElement("#ia_input_image");
            await setGradioImage(destination, blob, "rgba-composer-output.png");
        } catch (error) {
            console.error("Inpaint Anything transfer failed", error);
            window.alert(`Inpaint Anythingへの転送に失敗しました: ${error.message}`);
        }
        return [];
    };

    function setup() {
        setupLayerList();
        setupUndoExpiry();
        setupKeyboard();
        injectSourceButtons();
    }

    onUiLoaded(setup);
    onUiUpdate(setup);
})();
