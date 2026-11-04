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
    const label = generateButton.querySelector(".generate-label");
    const resultLoading = document.getElementById("result-loading");
    const resultLoadingMessage = document.getElementById(
        "result-loading-message"
    );
    const resultContent = document.getElementById("result-content");
    const pendingJob = document.getElementById("pending-job");

    let pollTimer = null;
    let pollController = null;
    let pollingVersion = 0;
    let jobEnded = false;

    function setGenerating(isGenerating, phase = "generating") {
        generateButton.disabled = isGenerating;
        generationStatus.hidden = !isGenerating;

        const messages = {
            submitting: {
                label: "Submitting",
                text: "Submitting your images. Please wait.",
            },
            queued: {
                label: "Queued",
                text: "Your image is queued and will start when the worker is available.",
            },
            generating: {
                label: "Generating",
                text: "Generating your image. This may take a few minutes.",
            },
        };

        if (isGenerating) {
            const message = messages[phase];

            label.textContent = message.label;
            generationStatus.textContent = message.text;

            if (resultLoadingMessage) {
                resultLoadingMessage.textContent = message.text;
            }

            generationForm.setAttribute("aria-busy", "true");
        } else {
            label.textContent = "Generate image";
            generationForm.removeAttribute("aria-busy");
        }

        if (resultLoading) {
            resultLoading.hidden = !isGenerating;
        }

        if (resultContent) {
            resultContent.hidden = isGenerating;
        }
    }

    function stopPolling() {
        pollingVersion += 1;
        window.clearTimeout(pollTimer);

        if (pollController) {
            pollController.abort();
            pollController = null;
        }
    }

    function showFailure(message) {
        jobEnded = true;
        stopPolling();
        setGenerating(false);

        generationStatus.textContent = message;
        generationStatus.hidden = false;
    }

    function showConnectionIssue() {
        const message =
            "Status is temporarily unavailable. We will keep checking automatically.";

        generationStatus.textContent = message;
        generationStatus.hidden = false;

        if (resultLoadingMessage) {
            resultLoadingMessage.textContent = message;
        }
    }

    async function checkStatus(version) {
        if (version !== pollingVersion || jobEnded) {
            return;
        }

        const controller = new AbortController();
        pollController = controller;

        try {
            const response = await fetch(pendingJob.dataset.statusUrl, {
                credentials: "same-origin",
                cache: "no-store",
                signal: controller.signal,
                headers: {
                    Accept: "application/json",
                },
            });

            const data = await response.json().catch(() => null);

            if (version !== pollingVersion) {
                return;
            }

            if (response.status === 503 || response.status >= 500) {
                showConnectionIssue();
                return;
            }

            if (!response.ok) {
                showFailure(
                    data?.message ??
                    "This generation is unavailable. Please create another image."
                );
                return;
            }

            if (data?.status === "finished" && data.result_url) {
                jobEnded = true;
                stopPolling();
                window.location.replace(data.result_url);
                return;
            }

            if (data?.status === "queued") {
                setGenerating(true, "queued");
                return;
            }

            if (data?.status === "generating") {
                setGenerating(true, "generating");
                return;
            }

            showFailure(
                data?.message ??
                "Image generation failed. Please try again."
            );
        } catch (error) {
            if (version !== pollingVersion) {
                return;
            }

            showConnectionIssue();
        } finally {
            if (pollController === controller) {
                pollController = null;
            }

            if (version === pollingVersion && !jobEnded) {
                pollTimer = window.setTimeout(
                    () => checkStatus(version),
                    Number(pendingJob.dataset.pollInterval)
                );
            }
        }
    }

    function startPolling() {
        stopPolling();
        setGenerating(true, "queued");
        checkStatus(pollingVersion);
    }

    generationForm.addEventListener("submit", function (event) {
        if (pendingJob && !jobEnded) {
            event.preventDefault();
            return;
        }

        setGenerating(true, "submitting");
    });

    window.addEventListener("pageshow", function () {
        if (pendingJob && !jobEnded) {
            startPolling();
        } else {
            setGenerating(false);
        }
    });

    window.addEventListener("pagehide", stopPolling);
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