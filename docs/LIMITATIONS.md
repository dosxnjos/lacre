# What Lacre cannot tell you

A green verdict means Lacre found nothing wrong in what it can read. It does not prove the phone was
never opened. Read this list before buying.

## The checks themselves

- **Replaced-part format not yet observed.** The way `FailureData` describes a swapped part
  (`SealedInstance` different from `LiveInstance`) is inferred from field names, not yet seen on a
  phone with a known replaced part. Any failure entry other than "Key is not required to seal"
  turns yellow, and a sealed/live mismatch turns red, so a failure is not silently ignored, but the
  exact wording of the result may need adjusting once a real case is seen. Reports of phones with
  known repairs are very welcome (sanitized, see [CONTRIBUTING.md](../CONTRIBUTING.md)).
- **Part dates are a heuristic.** The `PPP Y WW` date pattern in part serials is observed, not
  documented by Apple. A used part taken from another phone of the same era passes as OK. Third-party
  parts sometimes expose no serial at all (shown as "not verified", never as OK). A battery with
  replaced cells but the original controller board also passes.
- **Not every part is sealed or tracked.** The factory record covers what Apple seals on that model.
  Apple's own **Parts and Service History** (Settings → General → About) tracks only some parts
  ([Apple support article 102658](https://support.apple.com/102658)):

  | Model | Parts tracked by iOS |
  | --- | --- |
  | iPhone XR, XS, XS Max, SE (2nd and 3rd gen) | battery |
  | iPhone 11, 11 Pro, 11 Pro Max | battery, display |
  | iPhone 12 and later | battery, display, logic board, front camera, rear cameras |

  Things like the back glass, speakers, Lightning/USB-C port and (on iPhone 11) Face ID are not on
  that list. Labels: **Genuine** = replaced with an Apple part; **Unknown** = non-genuine or not
  verified; **Used** = an Apple part that came from another iPhone. The battery message
  "significantly degraded" is a wear warning, not a replacement.
- **MobileGestalt is closed.** Since iOS 17.4 the diagnostics service answers
  `MobileGestaltDeprecated` to the `SysCfg` keys. Lacre gets factory data only through the
  sysdiagnose, which needs the button press on the phone.
- **The factory check needs the seller's cooperation:** the phone must be unlocked, trusted, and
  left connected for 5 to 10 minutes. iOS leaves a screenshot in Photos when it starts.
- **Do not close Lacre during the factory check.** The sysdiagnose archive (~350 MB of the phone's
  logs) is deleted from the phone right after the download, together with any other archive that
  appeared during the check (for example from pressing the buttons twice, or right after cancelling).
  If the USB link drops, Lacre waits for the iPhone to come back and resumes where it stopped (giving up
  after 15 minutes without progress). Cleanup that cannot finish right away keeps retrying in the
  background; if the app is closed first, it resumes the next time Lacre opens with that iPhone
  connected. If that never happens, the archive stays on the phone until iOS prunes old diagnostics on
  its own. A "cleaning up" state that blocks closing the window is planned.
- **The Apple USB service can lose the iPhone while it keeps charging.** Charging and data are
  separate: the cable may still charge while the service no longer sees the phone. If the copy shows
  "connection lost" and does not resume in a few seconds, unplug and replug the cable with the iPhone
  unlocked.
- **Older diagnostics are only deleted when you ask.** Archives that were already on the phone before
  the check (the owner may have made them, for example for Apple Support) are listed after the check
  with a button to delete them; Lacre never deletes them on its own.
- **Every button press that vibrates starts a sysdiagnose** and leaves a screenshot in Photos, which
  Lacre does not touch.
- **No online lookups.** Lacre does not contact Apple or anyone else. Stolen/blocked IMEI status and
  warranty must be checked by hand (your country's IMEI registry, checkcoverage.apple.com).
- **Manual tests are manual.** The checklist and the touch page guide you; the result is what you
  observe. Ghost touch that appears only on mains power needs a wall charger, not a power bank.

## Platforms

- **Windows** needs Apple's free **Apple Devices** app (Microsoft Store) or iTunes, which provides
  the USB service. Lacre detects when it is missing.
- **macOS** works natively. Release builds are for Apple silicon only; Intel Macs must build from
  source. Installers are not code-signed or notarized yet (Windows SmartScreen and macOS Gatekeeper
  will warn on first launch).
- **Linux** has no installer yet; build from source and run `usbmuxd`.
- USB only. Wi-Fi connections are ignored on purpose.
- A charge-only cable, a loose connector or a front-panel/hub port can show up as "unknown USB
  device". Try another cable or a rear port before blaming the phone.

## Legal

Lacre is an independent open-source project. It is not affiliated with, endorsed by or sponsored by
Apple Inc. "iPhone" and "Apple" are trademarks of Apple Inc. The results are informational and come
without warranty (see [LICENSE](../LICENSE)); the decision to buy is yours.
