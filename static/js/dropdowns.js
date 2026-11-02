(() => {
    const mobile = window.matchMedia("(max-width: 700px)");
    const dropdowns = [];

    document.querySelectorAll(".select-control").forEach((control) => {
        const select = control.querySelector("select");
        if (!select) return;

        const label = document.querySelector(`label[for="${select.id}"]`);
        const originalTabindex = select.getAttribute("tabindex");
        const originalAriaHidden = select.getAttribute("aria-hidden");

        const trigger = document.createElement("button");
        trigger.type = "button";
        trigger.className = "select-trigger";
        trigger.id = `${select.id}-trigger`;
        trigger.setAttribute("role", "combobox");
        trigger.setAttribute("aria-haspopup", "listbox");
        trigger.setAttribute("aria-expanded", "false");
        trigger.setAttribute("aria-required", String(select.required));

        const text = document.createElement("span");
        text.className = "select-trigger-text";
        trigger.append(text);

        const list = document.createElement("ul");
        list.className = "select-options";
        list.id = `${select.id}-options`;
        list.setAttribute("role", "listbox");
        list.hidden = true;

        trigger.setAttribute("aria-controls", list.id);

        if (label) {
            if (!label.id) label.id = `${select.id}-label`;
            trigger.setAttribute("aria-labelledby", label.id);
            list.setAttribute("aria-labelledby", label.id);

            label.addEventListener("click", (event) => {
                if (mobile.matches) {
                    event.preventDefault();
                    trigger.focus();
                }
            });
        }

        const error = document.createElement("span");
        error.id = `${select.id}-error`;
        error.className = "select-error";
        error.textContent = "Please select an option.";
        error.hidden = true;
        trigger.setAttribute("aria-describedby", error.id);

        const options = [...select.options].filter(
            (option) => !option.disabled
        );

        let activeIndex = 0;
        let search = "";
        let searchTimer;

        const items = options.map((option, index) => {
            const item = document.createElement("li");
            item.id = `${select.id}-option-${index}`;
            item.setAttribute("role", "option");
            item.textContent = option.textContent;

            item.addEventListener("pointerdown", (event) => {
                event.preventDefault();
            });

            item.addEventListener("click", () => choose(index));

            list.append(item);
            return item;
        });

        control.append(trigger, list, error);
        select.classList.add("mobile-select-native");

        function setActive(index) {
            activeIndex = Math.max(0, Math.min(index, items.length - 1));

            items.forEach((item, position) => {
                item.classList.toggle("is-active", position === activeIndex);
            });

            if (!list.hidden && items[activeIndex]) {
                trigger.setAttribute(
                    "aria-activedescendant",
                    items[activeIndex].id
                );

                items[activeIndex].scrollIntoView({
                    block: "nearest",
                });
            }
        }

        function close() {
            list.hidden = true;
            trigger.setAttribute("aria-expanded", "false");
            trigger.removeAttribute("aria-activedescendant");
        }

        function open() {
            dropdowns.forEach((dropdown) => dropdown.close());

            list.hidden = false;
            trigger.setAttribute("aria-expanded", "true");

            const selectedIndex = options.findIndex(
                (option) => option.value === select.value
            );

            setActive(selectedIndex < 0 ? 0 : selectedIndex);
        }

        function sync() {
            text.textContent =
                select.selectedOptions[0]?.textContent ?? "";

            items.forEach((item, index) => {
                item.setAttribute(
                    "aria-selected",
                    String(options[index].value === select.value)
                );
            });

            if (select.validity.valid) {
                error.hidden = true;
                trigger.removeAttribute("aria-invalid");
            }
        }

        function choose(index) {
            select.value = options[index].value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            close();
            trigger.focus();
        }

        trigger.addEventListener("click", () => {
            if (list.hidden) open();
            else close();
        });

        trigger.addEventListener("keydown", (event) => {
            const key = event.key;

            if (key === "Escape") {
                close();
                event.preventDefault();
                return;
            }

            if (key === "Tab") {
                close();
                return;
            }

            if (key === "ArrowDown" || key === "ArrowUp") {
                event.preventDefault();

                if (list.hidden) {
                    open();
                } else {
                    setActive(activeIndex + (key === "ArrowDown" ? 1 : -1));
                }
                return;
            }

            if (key === "Home" || key === "End") {
                event.preventDefault();
                if (list.hidden) open();
                setActive(key === "Home" ? 0 : items.length - 1);
                return;
            }

            if (key === "Enter" || key === " ") {
                event.preventDefault();
                if (list.hidden) open();
                else choose(activeIndex);
                return;
            }

            if (
                key.length === 1 &&
                !event.ctrlKey &&
                !event.metaKey &&
                !event.altKey
            ) {
                event.preventDefault();
                if (list.hidden) open();

                clearTimeout(searchTimer);
                search += key.toLowerCase();

                const index = options.findIndex((option) =>
                    option.textContent.trim().toLowerCase().startsWith(search)
                );

                if (index >= 0) setActive(index);
                searchTimer = setTimeout(() => {
                    search = "";
                }, 700);
            }
        });

        select.addEventListener("change", sync);

        select.addEventListener("invalid", (event) => {
            if (!mobile.matches) return;

            event.preventDefault();
            error.hidden = false;
            trigger.setAttribute("aria-invalid", "true");

            const firstInvalid = select.form?.querySelector(":invalid");
            if (firstInvalid === select) trigger.focus();
        });

        control.addEventListener("focusout", (event) => {
            if (!control.contains(event.relatedTarget)) close();
        });

        select.form?.addEventListener("reset", () => {
            close();
            error.hidden = true;
            trigger.removeAttribute("aria-invalid");
            setTimeout(sync, 0);
        });

        function updateMode() {
            close();

            if (mobile.matches) {
                select.tabIndex = -1;
                select.setAttribute("aria-hidden", "true");
            } else {
                if (originalTabindex === null) {
                    select.removeAttribute("tabindex");
                } else {
                    select.setAttribute("tabindex", originalTabindex);
                }

                if (originalAriaHidden === null) {
                    select.removeAttribute("aria-hidden");
                } else {
                    select.setAttribute("aria-hidden", originalAriaHidden);
                }
            }

            sync();
        }

        dropdowns.push({ control, close, sync });
        mobile.addEventListener("change", updateMode);
        updateMode();
    });

    document.addEventListener("pointerdown", (event) => {
        dropdowns.forEach((dropdown) => {
            if (!dropdown.control.contains(event.target)) {
                dropdown.close();
            }
        });
    });

    window.addEventListener("pageshow", () => {
        dropdowns.forEach((dropdown) => {
            dropdown.close();
            dropdown.sync();
        });
    });
})();