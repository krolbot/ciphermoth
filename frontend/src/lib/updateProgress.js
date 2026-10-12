export const DONE_STATES = new Set(["success", "failed", "rolled_back", "intervention"]);

export const RECREATE_UPDATER_COMMAND =
  "docker compose -f docker-compose.prod.yml --profile autoupdate pull updater && \\\n" +
  "docker compose -f docker-compose.prod.yml --profile autoupdate up -d --no-deps updater";

export const START_UPDATER_COMMAND =
  "docker compose -f docker-compose.prod.yml --profile autoupdate up -d updater";

export const MANUAL_UPDATE_COMMAND =
  "docker compose -f docker-compose.prod.yml pull && \\\n" +
  "docker compose -f docker-compose.prod.yml up -d";

export const STATE_COPY = {
  requested: "Starting…",
  verifying: "Verifying image signatures…",
  snapshotting: "Backing up your database…",
  applying: "Applying update and restarting…",
  validating: "Checking the new version…",
  rolling_back: "Something went wrong, restoring the previous version…",
  success: "Updated. Reloading…",
  failed: "Update failed, your vault is untouched.",
  rolled_back: "Update failed and was rolled back, you're on the previous version.",
  intervention: "The update needs your attention, see the updater's logs.",
};

const stripV = (value) => String(value ?? "").replace(/^v/, "");

export const updaterMode = (apply) => {
  if (!apply) return "unknown";
  if (apply.updater_upgrade_required) return "upgrade";
  if (apply.updater_present) return "ready";
  if (apply.updater_protocol) return "stopped";
  return "absent";
};

export const progressOutcome = ({ status, requestId, live, boot, target, protocol }) => {
  if (protocol >= 2) {
    const state = status?.state;
    if (!state || !DONE_STATES.has(state)) return "waiting";
    if (status.id && requestId && status.id !== requestId) return "waiting";
    return state === "success" ? "success" : "failed";
  }
  const current = stripV(live);
  if (current && ((boot && current !== boot) || (target && current === stripV(target)))) {
    return "success";
  }
  const state = status?.state;
  if (state && DONE_STATES.has(state)) return state === "success" ? "success" : "failed";
  return "waiting";
};

export const failureMessage = (status) =>
  status?.detail || STATE_COPY[status?.state] || "The update did not finish.";
