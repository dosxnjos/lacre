# How Lacre works

This page explains where every result comes from and the rule that turns it into green, yellow or
red. What Lacre cannot see is in [LIMITATIONS.md](LIMITATIONS.md). The message format between the
app and the engine is in [PROTOCOL.md](PROTOCOL.md).

Lacre talks to the iPhone over USB through the usbmux service (Apple Devices on Windows, built into
macOS, `usbmuxd` on Linux), using the open-source [pymobiledevice3](https://github.com/doronz88/pymobiledevice3)
library. Every service it calls is read-only.

## 1. Quick read (about 40 seconds)

### Purchase blockers

| Check | Source on the phone | Rule |
| --- | --- | --- |
| Find My / Activation Lock | lockdown values, `NonVolatileRAM` → `fm-activation-locked` | `YES` = red (the phone stays tied to the seller's Apple Account). `NO` = green. Unreadable = yellow. |
| MDM / supervision | cloud configuration | supervised, non-removable MDM or an organization name = red. Another non-zero configuration source = yellow. |
| Configuration profiles | profile list | any profile = yellow (it can be harmless, like a DNS profile; ask the seller to remove it). |
| Activation state | lockdown `ActivationState` | `Activated` = green, anything else = yellow. |
| Origin | first letter of the model number (`ModelNumber`) | `M` new retail · `P` engraved (both green) · `N` Apple replacement · `F` Apple refurbished · `3`/`5` demo unit or third-party refurb · other = unknown (all yellow). The meaning of these prefixes is community knowledge, not published by Apple. |

A reading that fails never becomes green: it becomes yellow ("could not read") or makes the whole
verdict "incomplete".

### Part dates

Many parts carry a serial number readable from the IORegistry: rear and front cameras, Face ID
(infrared camera, dot projector), LiDAR, display components (`Panel_ID`, tokens separated by `+`)
and the battery (`BatteryData.Serial`). These serials follow a pattern of
**3 supplier characters + 1 year digit + 2 week digits** (`PPP Y WW`). The year digit is resolved to
a full year using the launch year of the phone's family.

The **assembly date** (the anchor) is the later of:

- the logic board serial (`mlb-serial-number`, same `PPP Y WW` pattern), and
- the old 12-character device serial (phones made until about mid-2021), where the 4th character is
  the year and half and the 5th is the week. The tables match those of `macserial` (OpenCore).

Each part is compared with the anchor:

| Part made… | Result |
| --- | --- |
| up to 10 weeks after assembly | green |
| 10 to 26 weeks after | yellow |
| more than 26 weeks after | red (likely replaced) |
| more than 18 months before | yellow |
| no readable serial / undecodable | not verified (never green) |

If the board and serial dates are more than four months apart, Lacre shows a notice (the board may
have been replaced, or the date reading does not apply to this model).

**This pattern is observed, not documented by Apple.** It is the weakest check, and the factory
check below replaces it when available.

### Battery

From the diagnostics battery data: cycle count (compared with Apple's rating of 500 cycles at 80%
up to iPhone 14, and 1000 cycles from iPhone 15), estimated capacity (`NominalChargeCapacity` and
`AppleRawMaxCapacity` over `DesignCapacity`, shown as an estimate only) and the battery's age
compared with the phone's age.

## 2. Factory check (5 to 10 minutes)

This is the strongest check. Every iPhone keeps a **factory data record (FDR)**: at the factory,
Apple seals the identity of key parts. iOS compares the installed parts with the sealed values and
includes the result in its diagnostic archive.

How Lacre gets it:

1. The buyer presses both volume buttons and the side button together for under one second. The
   phone vibrates and takes a screenshot: iOS has started a **sysdiagnose** (a diagnostic archive).
   Holding the buttons longer opens the power-off screen instead; cancel and try again.
2. The phone takes 5 to 10 minutes to build the archive (about 350 MB of logs).
3. Lacre downloads it to a temporary folder, reads **only** these two files, and deletes the archive
   from the computer and from the phone:
   - `logs/FDR/FDRDiagnosticReport.plist`
   - `logs/BatteryHealth/BatteryHealth.log`

   The download goes in 1 MB blocks with a 30-second watchdog. If the Apple USB service loses the
   phone (it can happen while the cable keeps charging), Lacre shows "connection lost", waits for the
   phone to come back and resumes from the same byte. Any other archive that appeared during the check
   (buttons pressed twice) is deleted too. Archives that were already on the phone are listed, and
   deleted only if you ask. That list does not need the factory check: Lacre reads it (read only)
   right after the quick read and shows it on the results screen.

What the report contains:

| Field | Meaning |
| --- | --- |
| `VerifiedData`, `VerifiedProperties` | parts and values that match what was sealed at the factory |
| `FailureData`, `FailureProperties` | entries that did not verify. If `SealedInstance` / `SealedProperty` differs from `LiveInstance` / `LiveProperty`, the installed part is not the one sealed at the factory: red. "Key is not required to seal" is informational and ignored. Any other failure is yellow. |
| `SealDate` | when the factory sealed the record (assembly) |
| `DataFailedToReport` | part of the data was not reported: yellow |
| `ApTicket` | anything other than `Trusted` is yellow |

`BatteryHealth.log` holds `Maximum Capacity Percent`, the same official health shown in
Settings → Battery. Rule: 85% or more is green, 80 to 84% yellow, under 80% red.

With a clean factory record (items verified, zero failures), the verdict no longer depends on the
part-date heuristic.

### How this method was found

On iOS 17.4 and later the diagnostics service refuses the MobileGestalt `SysCfg` keys that tools
used to read factory values from (`MobileGestaltDeprecated`). To find out how existing tools still
show factory values on new iOS, the public 3uTools installer was examined by **static analysis
only**: nothing was executed and no code was copied. The finding, a fact about the iPhone's own
interfaces, is that on new iOS it requests a sysdiagnose and reads the FDR report and the battery
health log from it. Lacre does the same, independently, with pymobiledevice3. This is
interoperability with data the phone already produces.

## 3. Manual tests

Some things only a person can check. The app shows a guided checklist where each item has a title,
how to test it, and a pass / fail / skip result that goes into the exported report. The list itself
lives in [`ui/src/checklist.ts`](../ui/src/checklist.ts). It covers, among others:

- **On the phone:** Settings → General → About → **Parts and Service History** (see the per-model
  table in [LIMITATIONS.md](LIMITATIONS.md)); Settings → Battery → **Battery Health** must show a
  percentage, not "Unable to verify this iPhone has a genuine Apple battery".
- **IMEI:** dial `*#06#`; the IMEIs must match the app, the box and the invoice. Check both IMEIs
  against your country's stolen-phone registry. Warranty and model: checkcoverage.apple.com.
- **Hardware:** microphones (record a voice memo and a video, play them back), earpiece and
  loudspeakers, headphones/Bluetooth audio output, Wi-Fi, Bluetooth, cellular and SIM, all cameras
  and the flash, Face ID or Touch ID, buttons and the silent switch, charging, vibration, proximity
  sensor (screen turns off during a call), True Tone and auto-brightness.
- **Screen:** solid colors to spot dead pixels, stains or burn-in, and the touch test below.
- **Closing the deal:** the seller signs out of iCloud and erases the phone in front of you, and you
  set it up with your own account before paying.

### Touch test

A faulty or poor-quality replacement screen can fail in ways a quick look misses:

- **Calibration offset:** the touch registers a few millimeters away from the finger (often below it).
- **Ghost touch:** touches happen without a finger, or a single touch jumps around the screen.
- **Dead zones:** parts of the screen that don't respond.

Some of these only appear **while the phone is charging from a wall outlet**: electrical noise from
the mains, through the charger, interferes with the touch controller. A **power bank** is a battery
that is not connected to the mains, so it can **hide** the problem. Bring a wall charger and ask
for an outlet; if the seller can't offer one, treat the touch test as not done.

The `touch-test/` page (a single standalone HTML file, served from GitHub Pages once the repository
is public; the app shows a QR code for it) is opened in Safari on the iPhone being checked. It draws
a cross where each touch was registered (so an offset from the fingertip is visible), fills a
coverage grid as you swipe over the whole screen, counts touches that happen while you are not
touching, and shows solid colors. Run it twice: once on battery, once plugged into the wall.

Without the page: open Notes, start a drawing, and slowly draw lines across the whole screen while
plugged into the wall. Lines should follow your finger exactly, with no gaps and no stray marks.
Scrolling a long feed in any social app for a minute is another quick check.

## 4. Verdict

The overall verdict follows these rules, in order (the reference implementation is `veredito()` in
[`engine/reference_conferir.py`](../engine/reference_conferir.py)):

1. Any red item → **red**: read the red items before paying.
2. Factory record verified with no failures → **green**, or **yellow** if anything else is yellow
   or there are notices.
3. Without the factory record: no assembly date, or no camera, display or battery could be dated →
   **incomplete** (yellow).
4. Otherwise, any yellow item or notice → **yellow**; else **green**, meaning the dates are consistent
   and nothing blocks the purchase. A same-era used part can still pass, so do the manual tests too.
