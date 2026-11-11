// Vanilla JS application bootstrap and theme management.
(function () {
    "use strict";

    function getSavedTheme() {
        // Allow URL override e.g. ?theme=dark for testing/screenshots
        try {
            const urlParams = new URLSearchParams(window.location.search);
            const urlTheme = urlParams.get("theme");
            if (urlTheme === "dark" || urlTheme === "light") {
                return urlTheme;
            }
        } catch (e) {
            // URLSearchParams not available or invalid
        }

        try {
            return localStorage.getItem("theme") || "light";
        } catch (e) {
            return "light";
        }
    }

    function saveTheme(theme) {
        try {
            localStorage.setItem("theme", theme);
        } catch (e) {
            // localStorage unavailable (e.g. cookies disabled, private browsing)
        }
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-bs-theme", theme);
        updateToggleButton(theme);
        window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: theme } }));
    }

    function updateToggleButton(theme) {
        const toggleBtn = document.getElementById("themeToggle");
        if (!toggleBtn) return;

        const isDark = theme === "dark";
        toggleBtn.setAttribute("aria-pressed", isDark ? "true" : "false");
        toggleBtn.innerHTML = isDark
            ? '<i class="bi bi-sun me-1" aria-hidden="true"></i> Light mode'
            : '<i class="bi bi-moon me-1" aria-hidden="true"></i> Dark mode';
    }

    // Initialize theme on DOMContentLoaded
    document.addEventListener("DOMContentLoaded", () => {
        const initialTheme = getSavedTheme();
        applyTheme(initialTheme);

        const toggleBtn = document.getElementById("themeToggle");
        if (toggleBtn) {
            toggleBtn.addEventListener("click", () => {
                const currentTheme = document.documentElement.getAttribute("data-bs-theme") || "light";
                const nextTheme = currentTheme === "dark" ? "light" : "dark";
                saveTheme(nextTheme);
                applyTheme(nextTheme);
            });
        }
    });
})();
