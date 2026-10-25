(function () {
  function initUiSwitcher() {
    if (document.getElementById("vcclient-ui-switcher")) return;
    if (!document.body) {
      window.requestAnimationFrame(initUiSwitcher);
      return;
    }

    const currentPath = window.location.pathname;
    const isClassic = currentPath.includes("/2.0.78");

    const container = document.createElement("div");
    container.id = "vcclient-ui-switcher";
    container.setAttribute("aria-label", "UI Version Switcher");
    container.style.cssText = [
      "position: fixed",
      "top: 8px",
      "right: 12px",
      "z-index: 999999",
      "display: inline-flex",
      "align-items: center",
      "gap: 6px",
      "background: rgba(24, 24, 27, 0.85)",
      "backdrop-filter: blur(8px)",
      "-webkit-backdrop-filter: blur(8px)",
      "border: 1px solid rgba(255, 255, 255, 0.2)",
      "border-radius: 6px",
      "padding: 3px 8px",
      "box-shadow: 0 2px 10px rgba(0, 0, 0, 0.35)",
      "font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      "font-size: 11px",
      "font-weight: 500",
      "color: #e4e4e7",
      "user-select: none",
      "transition: background 0.2s ease, border-color 0.2s ease",
    ].join(";");

    container.onmouseenter = function () {
      container.style.background = "rgba(39, 39, 42, 0.95)";
      container.style.borderColor = "rgba(255, 255, 255, 0.35)";
    };
    container.onmouseleave = function () {
      container.style.background = "rgba(24, 24, 27, 0.85)";
      container.style.borderColor = "rgba(255, 255, 255, 0.2)";
    };

    const label = document.createElement("span");
    label.textContent = "UI:";
    label.style.cssText = "color: #a1a1aa; font-weight: 600; letter-spacing: 0.5px;";
    container.appendChild(label);

    const select = document.createElement("select");
    select.setAttribute("aria-label", "Select UI Version");
    select.style.cssText = [
      "background: transparent",
      "color: #fafafa",
      "border: none",
      "outline: none",
      "font-family: inherit",
      "font-size: 11px",
      "font-weight: 600",
      "cursor: pointer",
      "padding: 1px 2px",
    ].join(";");

    const options = [
      { text: "Modern (v2.1.4)", value: "/ui/2.1.4/", selected: !isClassic },
      { text: "Classic (v2.0.78)", value: "/ui/2.0.78/", selected: isClassic },
    ];

    options.forEach(function (opt) {
      const option = document.createElement("option");
      option.value = opt.value;
      option.textContent = opt.text;
      option.selected = opt.selected;
      option.style.cssText = "background: #18181b; color: #fafafa;";
      select.appendChild(option);
    });

    select.onchange = function () {
      if (this.value && this.value !== currentPath) {
        window.location.href = this.value;
      }
    };

    container.appendChild(select);
    document.body.appendChild(container);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initUiSwitcher);
  } else {
    initUiSwitcher();
  }
})();
