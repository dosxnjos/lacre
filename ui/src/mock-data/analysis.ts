// Hand-built Analysis matching what the engine computes (rules of veredito() in
// engine/reference_conferir.py) for the sanitized fixtures raw.json / fdr.json.
// Used only by the browser mock. No real device identifiers here.
import type { Analysis, Item, Section } from "../types";

const device: Analysis["device"] = {
  model_name: "iPhone 11",
  product_type: "iPhone12,1",
  ios: "26.6.2",
  name: "iPhone de Teste",
  serial: "DV6J110JH32D",
  imei: ["356000000000011", "356000000000029"],
  model_number: "MHDH3",
  region: "BR/A",
  assembly: "2022-07",
  assembly_source: "serial",
};

function purchase(clean: boolean): Section {
  const items: Item[] = [
    clean
      ? { code: "findmy_off", status: "ok", params: {} }
      : { code: "findmy_on", status: "alert", params: { account_masked: "t•••••@example.com" } },
    { code: "mdm_none", status: "ok", params: {} },
    clean
      ? { code: "profiles_none", status: "ok", params: {} }
      : { code: "profiles_installed", status: "warn", params: { count: 1, names: ["Example DNS"] } },
    { code: "activation_state", status: "ok", params: { state: "Activated" } },
    { code: "origin_prefix", status: "ok", params: { prefix: "M", kind: "new_retail" } },
  ];
  return { id: "purchase", items };
}

const parts: Section = {
  id: "parts",
  items: [
    { code: "part_date_ok", status: "ok", params: { part: "camera_back", serial: "DNL21026L4EG51C6D", made: "2022-03" } },
    { code: "part_date_ok", status: "ok", params: { part: "camera_ultrawide", serial: "DNL21055WJBQ8D618", made: "2022-03" } },
    { code: "part_date_ok", status: "ok", params: { part: "camera_front", serial: "DNM21749MVG103K1H", made: "2022-04" } },
    { code: "part_date_ok", status: "ok", params: { part: "faceid_ir", serial: "DNM21716JQXMF5M3Y", made: "2022-04" } },
    { code: "part_date_ok", status: "ok", params: { part: "faceid_projector", serial: "DN8211419XFTHFQ6J", made: "2022-03" } },
    { code: "faceid_pairing_ok", status: "ok", params: { value: "Valid" } },
    { code: "part_date_ok", status: "ok", params: { part: "display_component", index: 1, count: 4, serial: "F7C2148H5BHBL64CG", made: "2022-04" } },
    { code: "part_date_ok", status: "ok", params: { part: "display_component", index: 2, count: 4, serial: "F7C2143T8JVPVNMHE", made: "2022-04" } },
    { code: "part_date_ok", status: "ok", params: { part: "display_component", index: 3, count: 4, serial: "CX52128710DE2Y6W1", made: "2022-03" } },
    { code: "part_date_ok", status: "ok", params: { part: "display_component", index: 4, count: 4, serial: "C432084XLDKPFQ0JS", made: "2022-02" } },
    { code: "part_date_ok", status: "ok", params: { part: "battery", serial: "FL8220908G8P3QVJ0", made: "2022-05" } },
  ],
};

function battery(withFdr: boolean, healthy: boolean): Section {
  const items: Item[] = [];
  if (withFdr) {
    const pct = healthy ? 88 : 79;
    items.push({ code: "battery_health_official", status: pct >= 85 ? "ok" : pct >= 80 ? "warn" : "alert", params: { percent: pct } });
  }
  items.push(
    { code: "battery_health_estimate", status: "na", params: { nominal_pct: 78, raw_pct: 80, design_mah: 3092 } },
    { code: "battery_cycles", status: "na", params: { cycles: 1042, design_cycles: 500 } },
    { code: "battery_age_ok", status: "ok", params: { years_on: 4.4, device_years: 4.4 } },
  );
  return { id: "battery", items };
}

const factory: Section = {
  id: "factory",
  seal_date: "01/07/2022 01:17:04 GMT",
  verified_count: 50,
  failed_count: 0,
  items: [{ code: "fdr_summary", status: "ok", params: { verified: 50, failed: 0 } }],
};

const factoryMismatch: Section = {
  id: "factory",
  seal_date: "01/07/2022 01:17:04 GMT",
  verified_count: 49,
  failed_count: 1,
  items: [
    { code: "fdr_summary", status: "alert", params: { verified: 49, failed: 1 } },
    { code: "fdr_part_mismatch", status: "alert", params: { key: "GpCl", part: "display", sealed: "D9S3273D5TMDJ93PT-9WY8A94024Z4", live: "F0X0000000000000-0000000000000" } },
  ],
};

/** Scenarios: "default" (Find My on -> alert), "clean" (everything fine), "swap" (display swapped per FDR). */
export function mockAnalysis(scenario: string, withFdr: boolean): Analysis {
  const clean = scenario === "clean" || scenario === "swap";
  const sections: Analysis["sections"] = [
    purchase(clean),
    withFdr ? (scenario === "swap" ? factoryMismatch : factory) : null,
    parts,
    battery(withFdr, clean),
  ];
  const notices: Analysis["notices"] = withFdr ? [{ code: "screenshot_left_in_photos", params: {} }] : [];
  let verdict: Analysis["verdict"];
  const statuses = sections.flatMap((s) => (s ? s.items.map((i) => i.status) : []));
  if (statuses.includes("alert")) verdict = { status: "alert", code: "alert_items", params: {} };
  else if (withFdr) verdict = statuses.includes("warn") ? { status: "warn", code: "factory_ok_with_warnings", params: {} } : { status: "ok", code: "factory_ok", params: {} };
  else if (statuses.includes("warn")) verdict = { status: "warn", code: "warnings", params: {} };
  else verdict = { status: "ok", code: "dates_ok", params: {} };
  return { verdict, device: { ...device }, sections, notices };
}
