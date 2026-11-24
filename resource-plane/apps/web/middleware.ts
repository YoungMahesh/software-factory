import { NextResponse, type NextRequest } from "next/server";
import { isExemptFromBasicAuth, extractBasicAuth } from "./lib/auth-middleware";

export function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  if (isExemptFromBasicAuth(pathname)) {
    return NextResponse.next();
  }

  const expectedUser = process.env.BASIC_AUTH_USERNAME || process.env.CONTROL_PLANE_USERNAME || "admin";
  const expectedPass = process.env.BASIC_AUTH_PASSWORD || process.env.CONTROL_PLANE_PASSWORD;

  if (!expectedPass) {
    return NextResponse.next();
  }

  const auth = extractBasicAuth(request.headers.get("authorization"));
  if (!auth || auth.user !== expectedUser || auth.pass !== expectedPass) {
    return new Response("Unauthorized: DB Host Control Plane requires authentication.\n", {
      status: 401,
      headers: {
        "WWW-Authenticate": "Basic realm=\"DB Host Control Plane\", charset=\"UTF-8\"",
        "Content-Type": "text/plain; charset=utf-8",
      },
    });
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
