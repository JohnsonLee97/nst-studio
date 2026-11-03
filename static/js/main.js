function setupImagePreview(inputId, previewId, removeId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);
    const removeButton = document.getElementById(removeId);

    if (!input || !preview || !removeButton) {
        return;
    }

    const container = preview.closest(".photo-preview");

    if (!container) {
        return;
    }

    let previewUrl = null;

    function clearPreview() {
        container.hidden = true;
        preview.removeAttribute("src");

        if (previewUrl !== null) {
            URL.revokeObjectURL(previewUrl);
            previewUrl = null;
        }
    }

    input.addEventListener("change", function () {
        clearPreview();

        const file = input.files[0];

        if (!file) {
            return;
        }

        previewUrl = URL.createObjectURL(file);
        preview.src = previewUrl;
        container.hidden = false;
    });

    removeButton.addEventListener("click", function () {
        input.value = "";
        clearPreview();
        input.focus();
    });
}

setupImagePreview(
    "content-image",
    "content-preview",
    "remove-content"
);

setupImagePreview(
    "style-image",
    "style-preview",
    "remove-style"
);

const generationForm = document.getElementById("generation-form");
const generateButton = document.getElementById("generate-button");
const generationStatus = document.getElementById("generation-status");

if (generationForm && generateButton && generationStatus) {
    // const spinner = generateButton.querySelector(".generation-spinner");
    const label = generateButton.querySelector(".generate-label");

    function setGenerating(isGenerating) {
        generateButton.disabled = isGenerating;

        label.textContent = isGenerating
            ? "Generating"
            : "Generate image";

        // spinner.hidden = !isGenerating;
        generationStatus.hidden = !isGenerating;

        const resultLoading = document.getElementById("result-loading");
        const resultContent = document.getElementById("result-content");

        if (resultLoading) {
            resultLoading.hidden = !isGenerating;
        }

        if (resultContent) {
            resultContent.hidden = isGenerating;
        }

        if (isGenerating) {
            generationForm.setAttribute("aria-busy", "true");
        } else {
            generationForm.removeAttribute("aria-busy");
        }
    }
    generationForm.addEventListener("submit", function () {
        setGenerating(true);
    });

    window.addEventListener("pageshow", function () {
        setGenerating(false);
    });
}

document.querySelectorAll(".drop-zone").forEach(function (zone) {
    const input = zone.querySelector('input[type="file"]');

    zone.addEventListener("dragover", function (event) {
        event.preventDefault();
        zone.classList.add("is-dragging");
    });

    zone.addEventListener("dragleave", function (event) {
        if (!zone.contains(event.relatedTarget)) {
            zone.classList.remove("is-dragging");
        }
    });

    zone.addEventListener("drop", function (event) {
        event.preventDefault();
        zone.classList.remove("is-dragging");

        const files = event.dataTransfer.files;

        if (files.length !== 1) {
            alert("Please drop one image at a time.");
            return;
        }

        const allowedTypes = ["image/jpeg", "image/png"];

        if (!allowedTypes.includes(files[0].type)) {
            alert("Please choose a JPG or PNG image.");
            return;
        }

        input.files = files;

        input.dispatchEvent(
            new Event("change", { bubbles: true })
        );
    });
});

document.querySelectorAll(".select-control").forEach(function (control) {
    const select = control.querySelector("select");
    const clearButton = control.querySelector(".clear-selection");

    if (!select || !clearButton) {
        return;
    }

    function updateClearButton() {
        clearButton.disabled = select.value === "";
    }

    select.addEventListener("change", updateClearButton);

    clearButton.addEventListener("click", function () {
        select.value = "";

        select.dispatchEvent(
            new Event("change", { bubbles: true })
        );

        select.focus();
    });

    window.addEventListener("pageshow", updateClearButton);

    updateClearButton();
});