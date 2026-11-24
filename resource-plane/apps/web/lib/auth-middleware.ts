export function isExemptFromBasicAuth(pathname: string): boolean {
  if (pathname === "/mcp" || pathname.startsWith("/mcp/") || pathname.startsWith("/api/mcp")) {
    return true;
  }
  if (pathname === "/api/ca.crt" || pathname === "/api/health") {
    return true;
  }
  if (pathname.startsWith("/_next") || pathname === "/favicon.ico") {
    return true;
  }
  return false;
}

export function extractBasicAuth(authHeader: string | null): { user: string; pass: string } | null {
  if (!authHeader || !authHeader.toLowerCase().startsWith("basic ")) return null;
  try {
    const b64 = authHeader.slice(6).trim();
    const decoded = atob(b64);
    const idx = decoded.indexOf(":");
    if (idx === -1) return null;
    return { user: decoded.slice(0, idx), pass: decoded.slice(idx + 1) };
  } catch {
    return null;
  }
}
