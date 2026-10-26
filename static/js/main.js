function setupImagePreview(inputId, previewId) {
    const input = document.getElementById(inputId);
    const preview = document.getElementById(previewId);

    let previewUrl = null;

    input.addEventListener("change", function () {
        if (previewUrl !== null) {
            URL.revokeObjectURL(previewUrl);
            previewUrl = null;
        }

        const file = input.files[0];

        if (!file) {
            preview.removeAttribute("src");
            preview.hidden = true;
            return;
        }

        previewUrl = URL.createObjectURL(file);
        preview.src = previewUrl;
        preview.hidden = false;
    });
}

setupImagePreview("content-image", "content-preview");
setupImagePreview("style-image", "style-preview");