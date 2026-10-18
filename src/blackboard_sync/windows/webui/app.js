// Blackboard Sync main window (WebView2). Draws the state Python sends and reports clicks.
//
// Every text arrives in the state and is set with textContent (append of a string
// makes a text node), never parsed as HTML. A click sends back only an id the state
// carried; Python checks it before acting (windows/web_window.py).
"use strict";

(() => {
  const STATE_ICONS = {
    synced: "check_circle-fill",
    syncing: "sync",
    paused: "pause_circle-fill",
    attention: "warning-fill",
    error: "error-fill",
  };
  const FILE_ICONS = {
    pdf: "picture_as_pdf",
    slides: "slideshow",
    doc: "description",
    sheet: "table_chart",
    archive: "folder_zip",
    image: "image",
    note: "article",
    other: "draft",
  };
  const RECENT_SAMPLE_MS = 500; // under the 1 s gap after which RecentSeen starts the exposure over

  let state = null;
  const drawn = {};

  // -- helpers --------------------------------------------------------------

  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat()) {
      if (child !== null && child !== undefined && child !== false) el.append(child);
    }
    return el;
  }

  function icon(name, cls) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", cls ? `icon ${cls}` : "icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }

  function call(name, ...args) {
    const api = window.pywebview && window.pywebview.api;
    if (api && typeof api[name] === "function") return api[name](...args);
    (window.__calls = window.__calls || []).push([name, ...args]); // the preview records clicks
    return Promise.resolve(null);
  }

  function changed(region, value) {
    const text = JSON.stringify(value);
    if (drawn[region] === text) return false;
    drawn[region] = text;
    return true;
  }

  // -- menus ----------------------------------------------------------------

  const menu = document.getElementById("menu");
  let menuAnchor = null;

  function openMenu(anchor, items, header) {
    menu.replaceChildren(
      header ? h("div", { class: "menu-header", text: header }) : null,
      items.map((item) => h("button", {
        class: "menu-item", type: "button", role: "menuitem", disabled: item.disabled,
        onclick: () => { menu.hidePopover(); item.run(); },
      }, icon(item.icon), h("span", { text: item.title }))),
    );
    menuAnchor = anchor;
    anchor.setAttribute("aria-expanded", "true");
    menu.showPopover();
    const box = anchor.getBoundingClientRect();
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    const left = Math.max(8, Math.min(box.right - width, window.innerWidth - width - 8));
    const below = box.bottom + 6;
    const top = below + height > window.innerHeight - 8 ? Math.max(8, box.top - height - 6) : below;
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menu.querySelector(".menu-item:not(:disabled)")?.focus();
  }

  menu.addEventListener("toggle", (event) => {
    if (event.newState === "closed" && menuAnchor) {
      menuAnchor.setAttribute("aria-expanded", "false");
      menuAnchor = null;
    }
  });

  // -- frame ----------------------------------------------------------------

  function drawTexts() {
    if (!changed("text", state.text)) return;
    for (const el of document.querySelectorAll("[data-text]")) {
      el.textContent = state.text[el.dataset.text] || "";
    }
    document.title = state.text.window_title;
  }

  function drawNav() {
    if (!changed("nav", [state.nav, state.section])) return;
    const nav = document.getElementById("nav");
    nav.replaceChildren(...state.nav.map((item) => {
      const active = item.id === state.section;
      return h("button", {
        class: "nav-item", type: "button", "aria-current": active ? "page" : null,
        onclick: () => navigate(item.id),
      }, icon(active ? `${item.icon}-fill` : item.icon), h("span", { class: "label", text: item.title }),
      item.badge ? h("span", { class: "badge", text: item.badge }) : null);
    }));
  }

  function drawChrome() {
    const chrome = state.chrome;
    if (!changed("chrome", chrome)) return;
    document.getElementById("actions").hidden = !chrome.shows_account;
    const pause = document.getElementById("pause");
    pause.disabled = !chrome.pause.enabled;
    pause.title = chrome.pause.title;
    pause.setAttribute("aria-label", chrome.pause.title);
    pause.querySelector("use").setAttribute("href", chrome.pause.paused ? "#i-play_circle" : "#i-pause_circle");
    const gear = document.getElementById("gear");
    gear.title = state.text.settings;
    gear.setAttribute("aria-label", state.text.settings);
    const avatar = document.getElementById("avatar");
    avatar.textContent = chrome.account.initials;
    avatar.title = chrome.account.name;
    avatar.setAttribute("aria-label", chrome.account.name);
    avatar.classList.toggle("warning", chrome.account.warning);
  }

  function drawHeading() {
    let heading = "";
    let subtitle = "";
    if (state.page === "overview") {
      heading = state.home.heading;
      subtitle = state.home.subtitle;
    } else {
      const item = state.nav.find((entry) => entry.id === state.section);
      heading = item ? item.title : state.text.settings;
    }
    document.getElementById("heading").textContent = heading;
    document.getElementById("subtitle").textContent = subtitle;
  }

  // -- Home -----------------------------------------------------------------

  function banner() {
    const data = state.banner;
    if (!data) return null;
    return h("section", { class: "banner" }, icon("download"),
      h("div", { class: "banner-text" },
        h("div", { class: "banner-title", text: data.title }),
        h("div", { class: "banner-detail", text: state.text.update_intro })),
      h("button", { class: "pill filled", type: "button", disabled: !data.enabled, onclick: () => call("action", "update") },
        data.button));
  }

  function fileRow(row) {
    const more = h("button", {
      class: "icon-button more", type: "button", "aria-haspopup": "menu", "aria-expanded": "false",
      "aria-label": row.name, title: row.name,
      onclick: (event) => {
        event.stopPropagation();
        openMenu(more, [
          { icon: "open_in_new", title: state.text.open, run: () => call("open_file", row.id) },
          { icon: "folder_open", title: state.text.show_in_folder, run: () => call("reveal_file", row.id) },
        ]);
      },
    }, icon("more_vert"));
    return h("div", { class: "row file-row", "data-id": row.id },
      h("button", { class: "row-main", type: "button", title: row.name, onclick: () => call("open_file", row.id) },
        h("span", { class: `file-chip ${row.kind}` }, icon(FILE_ICONS[row.kind] || FILE_ICONS.other)),
        h("span", { class: "row-text" },
          h("div", { class: "row-title", text: row.name }),
          h("div", { class: "row-detail", text: row.detail }))),
      row.new ? h("span", { class: "new-badge", text: state.text.new }) : icon("check_circle-fill", "done"),
      more);
  }

  function scene(line) {
    return [
      h("div", { class: "scene", "aria-hidden": "true" },
        icon("folder_open", "folder"), icon("draft", "paper"), icon("picture_as_pdf", "paper"), icon("slideshow", "paper")),
      line ? h("div", { class: "scene-line", text: line }) : null,
    ];
  }

  function statusCard(home) {
    const button = home.button && h("button", {
      class: "pill gray", type: "button", disabled: !home.button.enabled,
      onclick: () => call("action", home.button.id),
    }, home.button.title);
    const recent = home.scene === "first"
      ? scene(home.scene_line === home.detail ? "" : home.scene_line)
      : h("div", { class: "recent" },
        home.recent.length ? home.recent.map(fileRow) : h("div", { class: "empty", text: state.text.recent_empty }));
    return h("section", { class: "card status" },
      h("div", { class: "status-head" },
        icon(STATE_ICONS[home.state] || STATE_ICONS.synced, `state-icon ${home.state}`),
        h("div", { class: "state-text" },
          h("div", { class: "state-title", text: home.title }),
          h("div", { class: "state-detail", text: home.detail, title: home.detail })),
        button),
      home.message ? h("p", { class: home.message_warning ? "message warning" : "message", text: home.message }) : null,
      recent,
      h("div", { class: "card-footer" },
        h("button", { class: "pill tonal", type: "button", onclick: () => navigate("activity") }, state.text.view_all),
        h("span", { class: "count", text: home.recent_count })));
  }

  function listRow(iconName, row, kind) {
    return h("div", { class: "row list" },
      h("button", { class: "row-main", type: "button", title: row.title, onclick: () => call(kind, row.id) },
        h("span", { class: "deadline-icon" }, icon(iconName)),
        h("span", { class: "row-text" },
          h("div", { class: "row-title", text: row.title }),
          h("div", { class: "row-detail", text: row.detail }))));
  }

  function attentionRow(item) {
    return h("div", { class: "row attention-row attention" },
      icon(item.warning ? "warning-fill" : "notifications", item.warning ? "attention-icon" : "attention-icon info"),
      h("div", { class: "row-text" },
        h("div", { class: "row-title", text: item.title }),
        h("div", { class: "row-detail", text: item.detail }),
        item.id && item.action_title
          ? h("button", { class: "pill tonal small", type: "button", onclick: () => call("attention", item.id) },
            item.action_title)
          : null));
  }

  function announcementsCard(home) {
    const any = home.attention.length || home.announcements.length;
    return h("section", { class: "card" },
      h("h2", { class: "card-title", text: state.text.announcements }),
      any ? null : h("div", { class: "empty" },
        h("div", { class: "empty-title" }, icon("check_circle-fill"), h("span", { text: state.text.all_good })),
        h("div", { text: state.text.all_good_detail })),
      home.attention.map(attentionRow),
      home.announcements.map((row) => listRow("campaign", row, "announcement")),
      any ? h("div", { class: "card-footer" },
        h("button", { class: "pill tonal", type: "button", onclick: () => navigate("announcements") }, state.text.view_all))
        : null);
  }

  function deadlinesCard(home) {
    return h("section", { class: "card" },
      h("h2", { class: "card-title", text: state.text.upcoming }),
      home.deadlines.length ? home.deadlines.map((row) => listRow("event_upcoming", row, "deadline"))
        : h("div", { class: "empty", text: home.deadlines_message }),
      h("div", { class: "card-footer" },
        h("button", { class: "pill tonal", type: "button", onclick: () => navigate("calendar") }, state.text.open_calendar)));
  }

  function homePage() {
    const home = state.home;
    return h("div", { class: "home" },
      banner(),
      h("div", { class: "column" }, statusCard(home)),
      h("div", { class: "column" }, announcementsCard(home), deadlinesCard(home)));
  }

  function drawContent() {
    const page = state.page === "overview" ? ["overview", state.home, state.banner, state.text] : [state.page];
    if (!changed("content", page)) return;
    const content = document.getElementById("content");
    const scroll = content.scrollTop;
    content.replaceChildren(state.page === "overview" ? homePage() : h("div", { class: "placeholder" }, "…"));
    content.scrollTop = scroll;
  }

  // -- actions --------------------------------------------------------------

  function navigate(section) {
    if (!state || section === state.section) return;
    call("navigate", section);
    // Drawn at once; Python's next state confirms it.
    state.section = section;
    state.page = section;
    render(state);
  }

  document.getElementById("open-folder").addEventListener("click", () => call("action", "folder"));
  document.getElementById("pause").addEventListener("click", () => call("action", "pause"));
  document.getElementById("gear").addEventListener("click", () => navigate("general"));
  document.getElementById("avatar").addEventListener("click", (event) => {
    const account = state.chrome.account;
    openMenu(event.currentTarget, [
      { icon: account.action === "login" ? "login" : "logout", title: account.action_title,
        disabled: !account.action_enabled, run: () => call("action", "account") },
      { icon: "settings", title: state.text.settings, run: () => navigate("general") },
    ], account.header);
  });

  // Which of the last files are on screen, while the window has the focus (RecentSeen).
  let sampling = false;
  setInterval(() => {
    const active = !!state && state.page === "overview" && document.visibilityState === "visible" && document.hasFocus();
    if (!active) {
      if (sampling) call("recent_visible", [], false);
      sampling = false;
      return;
    }
    sampling = true;
    const view = document.getElementById("content").getBoundingClientRect();
    const visible = [...document.querySelectorAll(".recent .file-row")].filter((row) => {
      const box = row.getBoundingClientRect();
      return box.bottom > Math.max(view.top, 0) && box.top < Math.min(view.bottom, window.innerHeight);
    }).map((row) => row.dataset.id);
    call("recent_visible", visible, true);
  }, RECENT_SAMPLE_MS);

  // -- entry ----------------------------------------------------------------

  function render(next) {
    state = next;
    drawTexts();
    drawNav();
    drawChrome();
    drawHeading();
    drawContent();
  }

  window.app = { render };

  if (window.__PREVIEW_STATE__) {
    render(window.__PREVIEW_STATE__);
  } else {
    window.addEventListener("pywebviewready", () => call("ready").then((first) => first && render(first)));
  }
})();
