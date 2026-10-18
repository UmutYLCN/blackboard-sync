// Blackboard Sync main window (WebView2). Draws the state Python sends and reports clicks.
//
// Every text arrives in the state and is set with textContent (append of a string
// makes a text node), never parsed as HTML. A click sends back only an id the state
// carried; Python checks it before acting (windows/web_window.py). The settings form
// is edited here and sent whole on Save; Python validates it.
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
  // The settings form as edited (Get started shares it); reset whenever the saved values change.
  let edits = null;
  let savedForm = "";
  let savedKey = ""; // the saved values and Python's form generation (a new one drops the edits)
  let pastTerm = "";

  // -- helpers --------------------------------------------------------------

  function h(tag, props, ...children) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(props || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "text") el.textContent = value;
      else if (key === "value") el.value = value;
      else if (key === "checked") el.checked = true;
      else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
      else el.setAttribute(key, value === true ? "" : value);
    }
    for (const child of children.flat(Infinity)) {
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

  function pill(title, style, onclick, props) {
    return h("button", { class: `pill ${style}`, type: "button", onclick, ...props }, title);
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

  function fileMenu(anchor, row) {
    openMenu(anchor, [
      { icon: "open_in_new", title: state.text.open, run: () => call("open_file", row.id) },
      { icon: "folder_open", title: state.text.show_in_folder, run: () => call("reveal_file", row.id) },
    ]);
  }

  function moreButton(row) {
    const more = h("button", {
      class: "icon-button more", type: "button", "aria-haspopup": "menu", "aria-expanded": "false",
      "aria-label": row.name, title: row.name,
      onclick: (event) => { event.stopPropagation(); fileMenu(more, row); },
    }, icon("more_vert"));
    return more;
  }

  // -- dialog ---------------------------------------------------------------

  const dialog = document.getElementById("dialog");
  let shownDialog = null;

  function drawDialog() {
    const data = state.dialog;
    if (!data) {
      if (dialog.open) dialog.close();
      shownDialog = null;
      return;
    }
    if (shownDialog === data.id) return;
    shownDialog = data.id;
    let checked = false;
    const detail = data.checkbox && data.checkbox.detail
      ? h("p", { class: "dialog-detail", text: data.checkbox.detail, hidden: true }) : null;
    const answer = (button) => {
      call("dialog_answer", data.id, button, checked);
      dialog.close();
    };
    dialog.replaceChildren(
      h("h2", { class: "dialog-title", text: data.title }),
      h("p", { class: "dialog-message", text: data.message }),
      data.checkbox ? h("label", { class: "check" },
        h("input", {
          class: "switch", type: "checkbox",
          onchange: (event) => { checked = event.target.checked; if (detail) detail.hidden = !checked; },
        }),
        h("span", { text: data.checkbox.label })) : null,
      detail,
      h("div", { class: "dialog-buttons" },
        data.buttons.map((button) => pill(button.title, button.style || "gray", () => answer(button.id),
          { "data-default": button.default ? "true" : null }))),
    );
    dialog.oncancel = (event) => { event.preventDefault(); answer(null); }; // Escape cancels
    dialog.showModal();
    dialog.querySelector('[data-default="true"]')?.focus();
  }

  // -- frame ----------------------------------------------------------------

  function drawTexts() {
    if (!changed("text", state.text)) return;
    for (const el of document.querySelectorAll("[data-text]")) {
      el.textContent = state.text[el.dataset.text] || "";
    }
    document.title = state.text.window_title;
  }

  function drawTheme() {
    document.documentElement.dataset.theme = state.theme || "system";
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
    if (!changed("chrome", [chrome, state.text.settings])) return;
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
    } else if (state.section === "general") {
      heading = state.text.settings;
    } else {
      const item = state.nav.find((entry) => entry.id === state.section);
      heading = item ? item.title : "";
    }
    document.getElementById("heading").textContent = heading;
    document.getElementById("subtitle").textContent = subtitle;
  }

  // -- shared pieces ------------------------------------------------------------

  function stateHead(data, button) {
    return h("div", { class: "status-head" },
      icon(STATE_ICONS[data.state] || STATE_ICONS.synced, `state-icon ${data.state}`),
      h("div", { class: "state-text" },
        h("div", { class: "state-title", text: data.title }),
        h("div", { class: "state-detail", text: data.detail, title: data.detail })),
      button);
  }

  function chip(kind) {
    return h("span", { class: `file-chip ${kind}` }, icon(FILE_ICONS[kind] || FILE_ICONS.other));
  }

  function listRow(iconName, row, kind) {
    return h("div", { class: "row list" },
      h("button", { class: "row-main", type: "button", title: row.title, onclick: () => call(kind, row.id) },
        h("span", { class: "icon-tile" }, icon(iconName)),
        h("span", { class: "row-text" },
          h("div", { class: "row-title", text: row.title }),
          h("div", { class: "row-detail", text: row.detail }))));
  }

  function attentionRow(item) {
    return h("div", { class: "row attention-row" },
      icon(item.warning ? "warning-fill" : "notifications", item.warning ? "attention-icon" : "attention-icon info"),
      h("div", { class: "row-text" },
        h("div", { class: "row-title", text: item.title }),
        h("div", { class: "row-detail", text: item.detail }),
        item.id && item.action_title
          ? pill(item.action_title, "tonal small", () => call("attention", item.id)) : null));
  }

  function scene(small) {
    return h("div", { class: small ? "scene small" : "scene", "aria-hidden": "true" },
      icon("folder_open", "folder"), icon("draft", "paper"), icon("picture_as_pdf", "paper"), icon("slideshow", "paper"));
  }

  // -- Home -----------------------------------------------------------------

  function banner() {
    const data = state.banner;
    if (!data) return null;
    return h("section", { class: "banner" }, icon("download"),
      h("div", { class: "banner-text" },
        h("div", { class: "banner-title", text: data.title }),
        h("div", { class: "banner-detail", text: state.text.update_intro })),
      pill(data.button, "filled", () => call("action", "update"), { disabled: !data.enabled }));
  }

  function fileRow(row) {
    return h("div", { class: "row file-row", "data-id": row.id },
      h("button", { class: "row-main", type: "button", title: row.name, onclick: () => call("open_file", row.id) },
        chip(row.kind),
        h("span", { class: "row-text" },
          h("div", { class: "row-title", text: row.name }),
          h("div", { class: "row-detail", text: row.detail }))),
      row.new ? h("span", { class: "new-badge", text: state.text.new }) : icon("check_circle-fill", "done"),
      moreButton(row));
  }

  function statusCard(home) {
    const button = home.button
      && pill(home.button.title, "gray", () => call("action", home.button.id), { disabled: !home.button.enabled });
    const recent = home.scene === "first"
      ? [scene(false), home.scene_line && home.scene_line !== home.detail
        ? h("div", { class: "scene-line", text: home.scene_line }) : null]
      : h("div", { class: "recent" },
        home.recent.length ? home.recent.map(fileRow) : h("div", { class: "empty", text: state.text.recent_empty }));
    return h("section", { class: "card status" },
      stateHead(home, button),
      home.message ? h("p", { class: home.message_warning ? "message warning" : "message", text: home.message }) : null,
      recent,
      h("div", { class: "card-footer" },
        pill(state.text.view_all, "tonal", () => navigate("activity")),
        h("span", { class: "count", text: home.recent_count })));
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
      any ? h("div", { class: "card-footer" }, pill(state.text.view_all, "tonal", () => navigate("announcements"))) : null);
  }

  function deadlinesCard(home) {
    return h("section", { class: "card" },
      h("h2", { class: "card-title", text: state.text.upcoming }),
      home.deadlines.length ? home.deadlines.map((row) => listRow("event_upcoming", row, "deadline"))
        : h("div", { class: "empty", text: home.deadlines_message }),
      h("div", { class: "card-footer" }, pill(state.text.open_calendar, "tonal", () => navigate("calendar"))));
  }

  function homePage() {
    const home = state.home;
    return h("div", { class: "home" },
      banner(),
      h("div", { class: "column" }, statusCard(home)),
      h("div", { class: "column" }, announcementsCard(home), deadlinesCard(home)));
  }

  // -- Get started ------------------------------------------------------------

  function field(name, props) {
    const error = state.settings.error_field === name && state.settings.error;
    return h("input", {
      class: error ? "input invalid" : "input", type: "text", value: edits[name], "data-key": `field-${name}`,
      spellcheck: "false", oninput: (event) => { edits[name] = event.target.value; drawSaveBar(); }, ...props,
    });
  }

  function chooseButton(title) {
    return pill(title, "gray", () => call("choose_folder").then((path) => {
      if (!path) return;
      edits.dest = path;
      const input = document.querySelector('[data-key="field-dest"]');
      if (input) input.value = path;
      drawSaveBar();
    }));
  }

  function startPage() {
    const data = state.start;
    return h("div", { class: "start" },
      h("div", {},
        h("h2", { class: "start-title", text: data.title }),
        h("p", { class: "hint", text: data.intro }),
        h("div", { class: "steps" }, data.steps.map((step, index) => h("div", { class: "step" },
          h("span", { class: "step-number", text: String(index + 1) }),
          h("div", {}, h("div", { class: "step-title", text: step.title }), h("div", { class: "step-text", text: step.text }))))),
        h("p", { class: "hint", text: data.reopen })),
      h("section", { class: "card" },
        h("h2", { class: "card-title", text: data.form_title }),
        h("label", { class: "field-label", text: data.url_label }),
        field("base_url", { placeholder: data.url_placeholder }),
        h("div", { class: "form-gap" }),
        h("label", { class: "field-label", text: data.dest_label }),
        h("div", { class: "inline" }, field("dest"), chooseButton(data.choose)),
        h("p", { class: "field-note", text: data.dest_note }),
        h("label", { class: "check" },
          h("input", {
            class: "switch", type: "checkbox", checked: edits.autostart, "data-key": "field-autostart",
            onchange: (event) => { edits.autostart = event.target.checked; },
          }),
          h("span", { text: data.autostart })),
        pill(data.button.title, "filled wide", () => call("save", edits, data.button.login),
          { disabled: !data.button.enabled }),
        data.message ? h("p", { class: data.message_warning ? "message warning" : "message", text: data.message }) : null));
  }

  // -- Sync activity ----------------------------------------------------------

  function activityPage() {
    const data = state.activity;
    return h("section", { class: "card" },
      stateHead(data, null),
      h("div", { class: "table-head" }, h("span", { text: data.columns[0] }), h("span", { text: data.columns[1] }),
        h("span", {}), h("span", {})),
      data.rows.length ? data.rows.map((row) => h("div", { class: "table-row file-row", title: row.status },
        h("button", { class: "row-main", type: "button", title: row.name, onclick: () => call("open_file", row.id) },
          chip(row.kind),
          h("span", { class: "row-text" },
            h("div", { class: "row-title", text: row.name }),
            h("div", { class: "row-detail", text: row.detail }))),
        h("span", { class: "size", text: row.size }),
        icon("check_circle-fill", "done"),
        moreButton(row)))
        : h("div", { class: "empty", text: data.empty }));
  }

  // -- Announcements ------------------------------------------------------------

  function announcementsPage() {
    const data = state.announcements;
    return h("div", {},
      h("p", { class: "hint", text: data.hint }),
      data.attention.length ? [
        h("h2", { class: "section-title", text: data.attention_title }),
        h("section", { class: "card" }, data.attention.map(attentionRow)),
        h("div", { class: "form-gap" }),
      ] : null,
      data.rows.length ? h("div", { class: "stack" }, data.rows.map((row) => h("section", {
        class: "card announcement", onclick: () => call("announcement", row.id),
      },
      h("div", { class: "meta", text: row.detail }),
      h("div", { class: "title", text: row.title }),
      row.preview ? h("div", { class: "preview", text: row.preview }) : null,
      h("div", { class: "card-footer" },
        pill(data.open, "tonal small", (event) => { event.stopPropagation(); call("announcement", row.id); })))))
        : h("div", { class: "empty", text: data.empty }));
  }

  // -- Courses ------------------------------------------------------------------

  function coursesPage() {
    const data = state.courses;
    return h("div", {},
      h("p", { class: "hint", text: data.hint }),
      h("p", { class: "hint", text: data.untick }),
      data.rows.length ? h("section", { class: "card" }, data.rows.map((row) => h("label", {
        class: row.enabled ? "row course" : "row course off",
      },
      h("input", {
        class: "switch", type: "checkbox", checked: row.enabled, "aria-label": row.title,
        onchange: (event) => call("toggle_course", row.id, event.target.checked),
      }),
      h("span", { class: "row-text" },
        h("div", { class: "row-title", text: row.title }),
        h("div", { class: "row-detail", text: row.detail })))))
        : h("div", { class: "empty", text: data.empty }));
  }

  // -- Calendar -----------------------------------------------------------------

  function calendarPage() {
    const data = state.calendar;
    const parts = [h("p", { class: "hint", text: data.hint })];
    if (data.message) parts.push(h("p", { class: "message warning", text: data.message }));
    if (!data.days.length) parts.push(h("div", { class: "empty", text: data.empty }));
    let section = null;
    for (const day of data.days) {
      if (day.past !== section) {
        section = day.past;
        parts.push(h("h2", { class: "section-title", text: day.past ? data.past : data.upcoming }));
        if (day.past) parts.push(h("p", { class: "hint", text: data.past_hint }));
      }
      parts.push(h("section", { class: day.past ? "card past" : "card" },
        h("h3", { class: "day-title", text: day.title }),
        day.rows.map((row) => h("div", { class: "row deadline" },
          h("span", { class: "time", text: row.time }),
          h("button", { class: "row-main", type: "button", title: row.title, onclick: () => call("deadline", row.id) },
            h("span", { class: "row-text" },
              h("div", { class: "row-title", text: row.title }),
              h("div", { class: "row-detail", text: row.course })))))));
      parts.push(h("div", { class: "form-gap" }));
    }
    return h("div", {}, parts);
  }

  // -- Settings -----------------------------------------------------------------

  function dirty() {
    return JSON.stringify(edits) !== savedForm;
  }

  function control(row) {
    if (row.control === "field") {
      return [field(row.field, { placeholder: row.placeholder || null, "aria-label": row.title }),
        row.button ? chooseButton(row.button) : null];
    }
    if (row.control === "popup") {
      let current;
      let onchange;
      if (row.field) {
        current = edits[row.field];
        onchange = (event) => {
          const choice = row.choices[event.target.selectedIndex];
          edits[row.field] = choice.value;
          drawSaveBar();
        };
      } else if (row.key === "theme") {
        current = state.settings.theme;
        onchange = (event) => {
          const value = row.choices[event.target.selectedIndex].value;
          document.documentElement.dataset.theme = value; // at once; Python saves it
          call("set_theme", value);
        };
      } else {
        if (!row.choices.some((choice) => choice.value === pastTerm)) pastTerm = row.choices[0] ? row.choices[0].value : "";
        current = pastTerm;
        onchange = (event) => { pastTerm = row.choices[event.target.selectedIndex].value; };
      }
      return h("select", {
        class: "select", disabled: !row.enabled || !row.choices.length, "aria-label": row.title,
        "data-key": `select-${row.key}`, onchange,
      }, row.choices.map((choice) => h("option", { selected: choice.value === current ? true : null }, choice.title)));
    }
    if (row.control === "switch") {
      return h("input", {
        class: "switch", type: "checkbox", checked: edits[row.field], "aria-label": row.title,
        disabled: !row.enabled, "data-key": `field-${row.field}`,
        onchange: (event) => { edits[row.field] = event.target.checked; drawSaveBar(); },
      });
    }
    if (row.control === "buttons") {
      return row.buttons.map((button) => pill(button.title, button.destructive ? "danger" : "gray",
        () => call("setting", button.key, ""), { disabled: !button.enabled }));
    }
    if (row.control === "button") {
      return [row.running ? scene(true) : null,
        pill(row.button, row.destructive ? "danger" : "gray",
          () => call("setting", row.key, row.key === "past_download" ? pastTerm : ""), { disabled: !row.enabled })];
    }
    return null;
  }

  function settingRow(row) {
    return h("div", { class: row.control === "field" ? "setting field" : "setting" },
      h("div", { class: "setting-text" },
        row.title ? h("div", { class: row.warning ? "setting-title warning" : "setting-title", text: row.title }) : null,
        row.detail ? h("div", { class: "setting-detail", text: row.detail }) : null),
      h("div", { class: "setting-control" }, control(row)));
  }

  function settingsPage() {
    const data = state.settings;
    return h("div", { class: "settings" },
      data.sections.map((section) => [
        h("h2", { class: section.danger ? "section-title danger" : "section-title", text: section.title }),
        h("section", { class: section.danger ? "card danger" : "card" },
          section.rows.filter((row) => !row.hidden).map(settingRow),
          section.notes.map((note) => h("div", { class: "note", text: note }))),
        section.footer ? h("p", { class: "footer-note", text: section.footer }) : null,
      ]),
      h("div", { class: "save-bar", id: "save-bar", hidden: true },
        h("span", { class: "text", id: "save-text" }),
        pill(state.text.cancel, "gray", () => {
          edits = JSON.parse(savedForm);
          call("cancel_form");
          drawn.content = null;
          drawContent();
        }),
        pill(state.text.save, "filled", () => call("save", edits, false))));
  }

  function drawSaveBar() {
    const bar = document.getElementById("save-bar");
    if (!bar) return;
    const error = state.settings.error;
    bar.hidden = !(dirty() || error);
    const text = document.getElementById("save-text");
    text.textContent = error || state.text.unsaved;
    text.classList.toggle("warning", !!error);
  }

  // -- content --------------------------------------------------------------

  const PAGES = {
    overview: () => homePage(),
    start: () => startPage(),
    activity: () => activityPage(),
    announcements: () => announcementsPage(),
    courses: () => coursesPage(),
    calendar: () => calendarPage(),
    general: () => settingsPage(),
  };
  const PAGE_DATA = {
    overview: () => [state.home, state.banner],
    start: () => [state.start, state.settings.error_field, state.settings.error],
    activity: () => state.activity,
    announcements: () => state.announcements,
    courses: () => state.courses,
    calendar: () => state.calendar,
    general: () => [state.settings.sections, state.settings.theme, state.settings.error_field],
  };

  function syncEdits() {
    const key = JSON.stringify([state.settings.values, state.settings.generation || 0]);
    if (key !== savedKey) {
      savedKey = key;
      savedForm = JSON.stringify(state.settings.values);
      edits = JSON.parse(savedForm);
      drawn.content = null; // the inputs show the saved values again
    }
  }

  function drawContent() {
    const page = PAGES[state.page] ? state.page : "overview";
    if (changed("content", [page, PAGE_DATA[page](), state.text])) {
      const content = document.getElementById("content");
      const scroll = content.scrollTop;
      // Keep the caret where the student is typing when the page is redrawn under it.
      const focused = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.key : null;
      const caret = focused && document.activeElement.selectionStart;
      content.replaceChildren(PAGES[page]());
      content.scrollTop = scroll;
      const again = focused && content.querySelector(`[data-key="${focused}"]`);
      if (again) {
        again.focus();
        if (typeof caret === "number" && again.setSelectionRange) again.setSelectionRange(caret, caret);
      }
    }
    drawSaveBar();
  }

  // -- actions --------------------------------------------------------------

  function navigate(section) {
    if (!state || section === state.section) return;
    call("navigate", section);
    // Drawn at once; Python's next state confirms it.
    state.section = section;
    state.page = section === "overview" && state.page === "start" ? "start" : section;
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
    syncEdits();
    drawTheme();
    drawTexts();
    drawNav();
    drawChrome();
    drawHeading();
    drawContent();
    drawDialog();
  }

  window.app = { render };

  // Python answers next_state as soon as there is a state newer than the one drawn
  // (or with null after a while), so the page is redrawn without Python calling in.
  async function follow() {
    let revision = 0;
    for (;;) {
      try {
        const next = await call("next_state", revision);
        if (next && next.revision > revision) {
          revision = next.revision;
          render(next.state);
        }
      } catch (error) {
        await new Promise((resume) => setTimeout(resume, 1000)); // the app is busy quitting or restarting
      }
    }
  }

  if (window.__PREVIEW_STATE__) {
    render(window.__PREVIEW_STATE__);
  } else if (window.pywebview && window.pywebview.api) {
    follow();
  } else {
    window.addEventListener("pywebviewready", follow, { once: true });
  }
})();
