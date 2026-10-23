# Helio Strap — smart-wake capability gates

## What is known, not inferred

- Zepp configures up to 10 alarms on Helio Strap; the strap itself vibrates at the alarm time. **Keep a separate Zepp alarm at the deadline**.
- Android Health Connect `SleepSessionRecord` contains full intervals **only after the sleep session ends**. Reading its `stages` field during the smart-wake window is NOT valid live inference.
- Zepp OS SDK `@zos/sensor Sleep.getSleepingStatus()` returns awake/asleep on supported **device apps**; `getStage()` returns device-side stage records (reported update interval ~30 minutes). Support of custom device apps on the screenless Helio Strap is **unverified**.
- Gadgetbridge advertises Helio Strap as *experimental*. Its Alarms Intent API requires Gadgetbridge to be installed, configured, connected and enabled. It does not give the caller a structured success response. It must not be presented as a solution for Zepp-paired users without controlled testing.

## Completed in phase 2

- `HealthConnectReader.exportPayload`: includes stage start/end/type when the vendor exposes them in a completed session; does not fabricate absent stages.
- `hc_sleep_stages`: record- and provider-scoped history; additive schema, bounded and validated intervals, atomic re-import, backward compatibility.
- `GET /v1/sleep-stage-history?day=YYYY-MM-DD`: authenticated, read-only, reports whether exact time ranges exist, with explicit `live_stage_available: false`.
- Web **Sveglia → Fasi del sonno — verifica dati**: shows historical intervals, provider origin, or why only summary data exist.

## Hardware integration required before auto-wake

1. With user consent and device awake, confirm the BLE firmware, Zepp OS service / endpoint availability, authentication and collision behavior with Zepp. Never unpair, reset or replace Zepp remotely.
2. Prove *live* (not post-session) data are available during the wake window. A genuine stage source must be timestamped, fresh and validated. Otherwise a calibrated HR+movement waking proxy is an experiment, not an identified sleep stage.
3. Calibrate an early-wake decision against multiple nights. Reject stale/missing measurements, deep/REM where actually reported, and all decisions outside the scheduled window. Stay asleep if evidence is insufficient.
4. Before any write, enumerate existing on-band alarms, reserve an empty dedicated slot, check the write acknowledgment, read back the exact scheduled alarm, then conduct an **awake, opt-in physical vibration test**. The existing Zepp deadline alarm stays active.
5. Verify all failure modes: no connection, smartphone idle, notifications restricted, battery optimization, DST changes, receiver crash, no ACK, unknown firmware. Failure must never cancel the Zepp backup.

## Deployment caution for this VPS

The user's live `/opt/benessere/source/benessere/health_sync.py` had local modifications. Do not `git reset --hard`, overwrite that file, or restart the Android receiver before inspecting its current contents. The Android update requires the **same verified signing identity** as the installed app, and server-side schema must be deployed before enabling stage payload uploads.

## References

- Zepp Helio alarm: https://support.amazfit.com/us/amazfit_helio_strap/docs/OSUldKzExovDlRxnMyCcH10dnL0
- Health Connect sleep lifecycle: https://developer.android.com/health-and-fitness/health-connect/experiences/sleep
- Zepp OS Sleep SDK: https://docs.zepp.com/docs/reference/device-app-api/newAPI/sensor/Sleep/
- Gadgetbridge Helio support: https://gadgetbridge.org/gadgets/wearables/amazfit/
- Gadgetbridge alarm intents: https://gadgetbridge.org/internals/automations/intents/alarms/
