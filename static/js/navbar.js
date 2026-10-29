const nav = document.querySelector(".site-nav");
const toggle = document.getElementById("nav-toggle");
const links = document.getElementById("nav-links");

if (nav && toggle && links) {
    const mobileView = window.matchMedia("(max-width: 700px)");

    function setMenuOpen(isOpen) {
        toggle.setAttribute("aria-expanded", String(isOpen));

        toggle.setAttribute(
            "aria-label",
            isOpen ? "Close navigation" : "Open navigation"
        );

        toggle.textContent = isOpen ? "×" : "☰";

        links.classList.toggle("is-open", isOpen);
        document.body.classList.toggle("nav-open", isOpen);
    }

    toggle.addEventListener("click", function () {
        const isOpen = toggle.getAttribute("aria-expanded") === "true";
        setMenuOpen(!isOpen);
    });

    document.addEventListener("click", function (event) {
        if (!nav.contains(event.target)) {
            setMenuOpen(false);
        }
    });

    nav.addEventListener("keydown", function (event) {
        const isOpen = toggle.getAttribute("aria-expanded") === "true";

        if (event.key === "Escape" && isOpen) {
            setMenuOpen(false);
            toggle.focus();
        }
    });

    nav.addEventListener("focusout", function (event) {
        if (!nav.contains(event.relatedTarget)) {
            setMenuOpen(false);
        }
    });

    mobileView.addEventListener("change", function () {
        setMenuOpen(false);
    });

    setMenuOpen(false);
}