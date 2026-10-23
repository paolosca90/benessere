# Smart Wake Helio Strap — first implementation stage

## Target

- The alert must VIBRATE THE STRAP, not play audio on the Pixel.
- User selects a maximum wake time and an earlier 15–30 minute wake window.
- The decision engine can recommend an early wake when there is fresh evidence of light/awake state or a calibrated joint movement/HR waking proxy.
- The joint HR/movement signal DOES NOT establish actual sleep stage; thresholds remain experimental.
- Zepp must keep an independently programmed on-band backup alarm at the deadline until our Bluetooth driver has been tested on the physical strap.
- Never poll Bluetooth all night. Acquire extra live data during the configured window only.

## What this branch actually implements

- Native Kotlin SmartWakeEngine: window checks, no stale samples, consecutive evidence, deep/REM veto, deadline handling.
- Native Kotlin ZeppOsAlarmCodec: creates the alarm request / create / delete byte payloads for endpoint 0x000f, without transmitting them or claiming success.
- JUnit tests plus local Kotlin compilation and six smoke checks. These tests use synthetic samples in code; NO synthetic measurements are written to the health diary.

**This branch DOES NOT make Helio vibrate yet.** It must not be deployed as a functioning smart alarm.

## Hardware integration and verification still needed

1. Get the actual Vultr Next.js PWA source and audit why the webapp alarm scheduled for the night did not fire. The installed PWA is not in the current repository checkout.
2. Implement and verify authenticated Zepp OS BLE transport on the existing Pixel/Android receiver. Current legacy Huami FEE1 handshake is not sufficient for Helio Strap; repository investigation points to FED0 write/notify transport.
3. Read the current alarm slots, reserve one truly unused slot, never overwrite Zepp-created alarms; send create and require both positive acknowledgement AND a read-back.
4. Perform explicit awake physical test: confirm vibration on Helio. Only then integrate alarm ownership, persistence and retry behavior.
5. Connect fresh heart rate and movement from REAL supported providers. Health Connect sleep session stages normally arrive after the session ends and are unsuitable as a live feed.
6. Wire the PWA alarm settings to the Android companion, persist across reboot and DST transitions, and show honest progression: saved -> device acknowledged -> physically tested.
7. Test disconnects, battery optimization, Zepp coexistence, time zone and exact alarm behavior on the Pixel 9 Pro XL.

## Protocol and platform sources

- Amazfit Helio Strap alarms: https://support.amazfit.com/us/amazfit_helio_strap/docs/OSUldKzExovDlRxnMyCcH10dnL0
- Android Health Connect sleep session lifecycle: https://developer.android.com/health-and-fitness/health-connect/experiences/sleep
- Gadgetbridge Helio Strap experimental support: https://gadgetbridge.org/gadgets/wearables/amazfit/
- Zepp OS alarm codec protocol reference (AGPL-3.0): https://github.com/zoop-dev/pulse/blob/01668257f6e19869b5fe54f314f9974c2b16553c/app/src/main/java/nodomain/freeyourgadget/gadgetbridge/service/devices/huami/zeppos/services/ZeppOsAlarmsService.java

Respect upstream licensing before copying or embedding Gadgetbridge implementation code.
