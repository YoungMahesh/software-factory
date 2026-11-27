const UTF8_ENCODER = new TextEncoder();

export function isExemptFromBasicAuth(pathname: string): boolean {
  if (
    pathname === "/api/health" ||
    pathname === "/favicon.ico" ||
    pathname === "/icon.svg"
  ) {
    return true;
  }
  if (pathname.startsWith("/_next")) {
    return true;
  }
  return false;
}

export function extractBasicAuth(authHeader: string | null): { user: string; pass: string } | null {
  if (!authHeader || !authHeader.toLowerCase().startsWith("basic ")) {
    return null;
  }
  try {
    const encoded = authHeader.slice(6).trim();
    const decoded = atob(encoded);
    const sepIndex = decoded.indexOf(":");
    if (sepIndex === -1) {
      return null;
    }
    return {
      user: decoded.slice(0, sepIndex),
      pass: decoded.slice(sepIndex + 1),
    };
  } catch {
    return null;
  }
}

export function constantTimeEqual(a: string, b: string): boolean {
  const bytesA = UTF8_ENCODER.encode(a);
  const bytesB = UTF8_ENCODER.encode(b);
  const maxLen = Math.max(bytesA.length, bytesB.length);
  let diff = bytesA.length ^ bytesB.length;
  for (let i = 0; i < maxLen; i += 1) {
    const byteA = i < bytesA.length ? bytesA[i] : 0;
    const byteB = i < bytesB.length ? bytesB[i] : 0;
    diff |= byteA ^ byteB;
  }
  return diff === 0;
}

export function unauthorizedBasicResponse(): Response {
  return new Response("Authentication required.\n", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Dashboard Deployer", charset="UTF-8"',
      "Content-Type": "text/plain; charset=utf-8",
    },
  });
}
