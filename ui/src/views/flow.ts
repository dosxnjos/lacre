// Screens before the results: startup, prerequisites, connect, reading.
import { h, svg } from "../dom";
import { t } from "../i18n";
import { connectArt, icons } from "../art";
import { modelName } from "../models";
import type { Ctx } from "../state";
import { READ_STEPS } from "../types";
import { button, errorBox, errorText } from "./common";

export function startupView({ s, act }: Ctx): HTMLElement {
  const d = t();
  if (s.phase === "engine_failed") {
    return h("section", { class: "screen screen-center" },
      h("div", { class: "panel narrow" },
        h("h1", { class: "title" }, d.startup.engineFailedTitle),
        h("p", { class: "lead" }, d.startup.engineFailedText),
        s.startupError && s.showTech ? h("p", { class: "mono small" }, `${s.startupError.code}: ${s.startupError.detail}`) : null,
        h("div", { class: "actions" }, button(d.common.retry, act.retryStartup, "primary")),
      ),
    );
  }
  return h("section", { class: "screen screen-center", "aria-busy": "true" },
    h("div", { class: "starting" }, h("span", { class: "spinner", "aria-hidden": "true" }), h("p", null, d.startup.starting)),
  );
}

export function prereqView({ s, act }: Ctx): HTMLElement {
  const d = t().startup;
  const linux = s.prereq?.hint === "usbmuxd_missing";
  return h("section", { class: "screen screen-center" },
    h("div", { class: "panel narrow" },
      svg(icons.store, "hero-icon"),
      h("h1", { class: "title" }, linux ? d.usbmuxdTitle : d.prereqTitle),
      h("p", { class: "lead" }, linux ? d.usbmuxdText : d.prereqText),
      linux ? null : h("ol", { class: "steps" },
        h("li", null, d.prereqStep1), h("li", null, d.prereqStep2), h("li", null, d.prereqStep3)),
      h("div", { class: "actions" },
        linux ? null : button(d.prereqButton, act.openStore, "primary"),
        button(t().common.retry, act.retryStartup, linux ? "primary" : "secondary"),
      ),
      h("p", { class: "fine" }, svg(icons.shield, "inline-icon"), d.prereqWhy),
    ),
  );
}

export function connectView({ s, act }: Ctx): HTMLElement {
  const d = t().connect;
  const lang = s.lang;
  const devices = s.devices;
  const notTrusted = s.connectError && ["not_trusted", "passcode_required"].includes(String(s.connectError.code));

  let status: HTMLElement;
  if (devices.length === 0) {
    status = h("div", { class: "searching", role: "status", "aria-live": "polite" },
      h("span", { class: "spinner small", "aria-hidden": "true" }),
      h("div", null,
        h("p", { class: "searching-title" }, notTrusted ? errorText(String(s.connectError!.code)).title : d.searching),
        h("p", { class: "muted" }, notTrusted ? d.trustHint : d.cableHint),
      ),
    );
  } else {
    const pick = devices.length > 1;
    status = h("div", { class: "found" },
      h("p", { class: "found-title", role: "status", "aria-live": "polite" }, pick ? d.pickOne : d.found),
      h("div", { class: "devices", role: pick ? "radiogroup" : null },
        devices.map((dev) => {
          const sel = dev.udid === s.selectedUdid;
          return h("button", {
            type: "button",
            class: `device${sel ? " is-selected" : ""}`,
            role: pick ? "radio" : null,
            "aria-checked": pick ? String(sel) : null,
            onclick: (() => act.selectDevice(dev.udid)) as EventListener,
          },
          h("span", { class: "device-glyph", "aria-hidden": "true" }),
          h("span", { class: "device-body" },
            h("span", { class: "device-name" }, dev.name || modelName(dev.product_type, lang)),
            h("span", { class: "device-meta" },
              h("span", null, modelName(dev.product_type, lang)),
              h("span", null, d.ios(dev.ios)),
            ),
          ),
          pick ? h("span", { class: "radio", "aria-hidden": "true" }) : null,
          );
        }),
      ),
      h("div", { class: "actions" },
        h("button", {
          type: "button", class: "btn btn-primary btn-large",
          disabled: !s.selectedUdid,
          onclick: act.startRead as EventListener,
        }, d.checkButton),
      ),
    );
  }

  return h("section", { class: "screen connect" },
    h("div", { class: "connect-art" }, svg(connectArt())),
    h("div", { class: "connect-body" },
      h("h1", { class: "title" }, d.title),
      h("p", { class: "lead" }, d.text),
      h("ol", { class: "steps" }, h("li", null, d.stepCable), h("li", null, d.stepUnlock), h("li", null, d.stepTrust)),
      status,
      h("p", { class: "fine" }, svg(icons.shield, "inline-icon"), d.privacy),
      h("div", { class: "demo-row" },
        h("span", { class: "muted" }, d.demoHint),
        h("button", { type: "button", class: "btn btn-quiet", "data-fk": "demo",
          onclick: act.startDemo as EventListener }, d.demoButton)),
    ),
  );
}

export function readingView({ s, act }: Ctx): HTMLElement {
  const d = t().reading;
  const r = s.read;
  if (r.error) {
    return h("section", { class: "screen screen-center" },
      h("div", { class: "panel narrow" },
        h("h1", { class: "title" }, d.failedTitle),
        errorBox(String(r.error.code), r.error.detail, s.showTech, act.startRead),
        h("div", { class: "actions" }, button(t().nav.another, act.restart, "quiet")),
      ),
    );
  }
  const total = READ_STEPS.length;
  const pct = Math.round((100 * r.done.length) / total);
  return h("section", { class: "screen screen-center" },
    h("div", { class: "panel narrow" },
      h("h1", { class: "title" }, d.title),
      h("p", { class: "lead" }, d.text),
      h("div", { class: "bar", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(pct) },
        h("span", { style: `width:${r.analyzing ? 100 : pct}%` })),
      h("ol", { class: "progress-steps" },
        READ_STEPS.map((step) => {
          const done = r.done.includes(step);
          const cur = !done && r.current === step;
          return h("li", { class: done ? "is-done" : cur ? "is-current" : "" },
            h("span", { class: "ps-mark", "aria-hidden": "true" }, done ? svg(icons.check) : cur ? h("span", { class: "spinner tiny" }) : null),
            h("span", null, d.steps[step]),
          );
        }),
        h("li", { class: r.analyzing ? "is-current" : "" },
          h("span", { class: "ps-mark", "aria-hidden": "true" }, r.analyzing ? h("span", { class: "spinner tiny" }) : null),
          h("span", null, d.analyzing)),
      ),
    ),
  );
}
