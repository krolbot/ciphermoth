export const planServiceAccessChanges = (current, desired) =>
  desired.flatMap((grant) => {
    const existing = current.find((share) => share.user_id === grant.user_id);
    if (grant.permission === "none") return existing ? [{ type: "revoke", ...grant }] : [];
    return !existing || existing.permission !== grant.permission ? [{ type: "set", ...grant }] : [];
  });
