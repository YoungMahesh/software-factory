import { NextResponse, type NextRequest } from "next/server";
import {
  constantTimeEqual,
  extractBasicAuth,
  isExemptFromBasicAuth,
  unauthorizedBasicResponse,
} from "./lib/auth";

export function middleware(request: NextRequest) {
  if (isExemptFromBasicAuth(request.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const expectedUser = process.env.WEB_UI_USERNAME;
  const expectedPass = process.env.WEB_UI_PASSWORD;

  if (!expectedUser || !expectedPass) {
    if (process.env.NODE_ENV === "production") {
      return new Response(
        "Server authentication misconfigured: WEB_UI_USERNAME and WEB_UI_PASSWORD must be set.\n",
        { status: 500, headers: { "Content-Type": "text/plain; charset=utf-8" } },
      );
    }
    return NextResponse.next();
  }

  const parsed = extractBasicAuth(request.headers.get("authorization"));
  if (
    !parsed ||
    !constantTimeEqual(parsed.user, expectedUser) ||
    !constantTimeEqual(parsed.pass, expectedPass)
  ) {
    return unauthorizedBasicResponse();
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg).*)"],
};
