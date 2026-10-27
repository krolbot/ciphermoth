export const toUtcExpiry = (value) => (value ? new Date(value).toISOString() : null);

export const toLocalExpiry = (value) => {
  if (!value) return "";
  const parsed = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
  const local = new Date(parsed.getTime() - parsed.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
};

export const isInvalidExpiry = (value) =>
  Boolean(value) && (!Number.isFinite(Date.parse(value)) || Date.parse(value) <= Date.now());
