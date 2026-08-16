export function isAppHostname(
  hostname: string,
  appHostname = process.env.NEXT_PUBLIC_APP_HOST,
): boolean {
  return Boolean(appHostname) && hostname.toLowerCase() === appHostname?.toLowerCase();
}

export function isDemoSquadEnabled(
  hostname: string,
  environment = process.env.NODE_ENV,
  appHostname = process.env.NEXT_PUBLIC_APP_HOST,
): boolean {
  return environment !== "production" || isAppHostname(hostname, appHostname);
}
