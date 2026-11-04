# Runbook: mobile app features

Flags for the mobile app and the kiosks live in `flags/mobile.json`. In an incident, switch a
feature off with its override variable on the mobile API (deploy/mobile-api.env), then redeploy;
the change takes effect in about two minutes. Write down what you switched in the incident ticket.

## Reorder button failing

Symptoms: reorder taps return 500s, or orders arrive twice.

1. Switch reordering off: set `FLAGKIT_ONE_TAP_REORDER=off` on the mobile API and redeploy.
2. The kiosks force reordering on (deploy/kiosk.env); switch them off the same way if the
   failures come from the shop floor.
3. Page the basket team.

## Offline cart losing items

1. It is off in production already (deploy/mobile-api.env); if a test cohort is affected, set
   `FLAGKIT_OFFLINE_CART=off` in their environment too.
2. Page the basket team.
