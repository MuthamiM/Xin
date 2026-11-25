/* Xin Shared Frontend Security, Theme, and Telemetry Controller */
(function (global) {
  "use strict";

  const ALLOWED_THEMES = new Set(["electric-blue", "cobalt-deep", "obsidian-steel"]);

  const XinShared = {
    getTheme: function () {
      try {
        const saved = localStorage.getItem("xin_theme");
        if (saved && ALLOWED_THEMES.has(saved)) {
          return saved;
        }
      } catch (e) {}
      return "electric-blue";
    },

    applyTheme: function (themeName) {
      const target = ALLOWED_THEMES.has(themeName) ? themeName : "electric-blue";
      document.documentElement.setAttribute("data-theme", target);
      try {
        localStorage.setItem("xin_theme", target);
      } catch (e) {}
      return target;
    },

    sanitizeSessionId: function (raw) {
      if (typeof raw !== "string") return "";
      return raw.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 48);
    },

    sanitizeMessageText: function (raw) {
      if (typeof raw !== "string") return "";
      return raw.replace(/[<>]/g, "").trim().slice(0, 2000);
    }
  };

  XinShared.applyTheme(XinShared.getTheme());
  global.XinShared = XinShared;
})(window);
