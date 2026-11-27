import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { T3LinksModal } from "@/components/modals/t3-links-modal";
import { proxyToControlPlane } from "@/lib/control-plane";
import {
  appendGeneratedT3Link,
  buildSandboxT3LinksPath,
  seedInitialT3Links,
} from "@/lib/t3-links";

describe("T3 pairing links modal helpers, rendering, and BFF proxy", () => {
  it("builds sandbox t3-links paths and seeds only tokenized pairing URLs", () => {
    expect(buildSandboxT3LinksPath("sb-1", "team a")).toBe(
      "/api/sandboxes/sb-1/t3-links?profile=team%20a",
    );
    expect(buildSandboxT3LinksPath("sb-1", null)).toBe(
      "/api/sandboxes/sb-1/t3-links",
    );

    expect(seedInitialT3Links(null)).toEqual([]);
    expect(seedInitialT3Links("https://t3.modal.host")).toEqual([]);
    expect(
      seedInitialT3Links("https://t3.modal.host/pair#token=ABC123"),
    ).toEqual([
      {
        url: "https://t3.modal.host/pair#token=ABC123",
        status: "active",
      },
    ]);
  });

  it("appends newly generated links at the end without duplicates", () => {
    const initial = [
      { id: "1", url: "https://t3.modal.host/pair#token=AAA", status: "used" as const },
      { id: "2", url: "https://t3.modal.host/pair#token=BBB", status: "active" as const },
    ];
    const appended = appendGeneratedT3Link(initial, {
      id: "3",
      url: "https://t3.modal.host/pair#token=CCC",
      status: "active",
    });
    expect(appended.map((l) => l.id)).toEqual(["1", "2", "3"]);

    const deduped = appendGeneratedT3Link(appended, {
      id: "2",
      url: "https://t3.modal.host/pair#token=BBB",
      status: "active",
    });
    expect(deduped.map((l) => l.id)).toEqual(["1", "3", "2"]);
  });

  it("renders T3LinksModal with plain non-clickable seeded URL, Copy button, and Generate button", () => {
    const html = renderToStaticMarkup(
      createElement(T3LinksModal, {
        target: {
          id: "sb-1",
          name: "my-sandbox",
          running: true,
          profile: "work",
          t3_pair_url: "https://t3.modal.host/pair#token=SEED123",
        },
        onClose: () => {},
        onToast: () => {},
      }),
    );

    expect(html).toContain("T3Code Pairing Links");
    expect(html).toContain("https://t3.modal.host/pair#token=SEED123");
    expect(html).not.toContain("<a ");
    expect(html).toContain("Copy");
    expect(html).toContain("Generate");
  });

  it("proxies GET and POST /api/sandboxes/:id/t3-links through BFF", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fakeFetch: typeof fetch = async (input, init) => {
      calls.push({ url: String(input), method: init?.method ?? "GET" });
      return Response.json({ ok: true });
    };

    const env = {
      NODE_ENV: "test",
      SANDBOX_CONTROL_PLANE_URL: "https://control.modal.run",
      WEB_UI_USERNAME: "admin",
      WEB_UI_PASSWORD: "secret",
    } as const;

    const getRes = await proxyToControlPlane(
      new Request("https://dash.example.com/api/sandboxes/sb-1/t3-links?profile=work"),
      ["sandboxes", "sb-1", "t3-links"],
      { fetchImpl: fakeFetch, env },
    );
    expect(getRes.status).toBe(200);

    const postRes = await proxyToControlPlane(
      new Request("https://dash.example.com/api/sandboxes/sb-1/t3-links?profile=work", {
        method: "POST",
      }),
      ["sandboxes", "sb-1", "t3-links"],
      { fetchImpl: fakeFetch, env },
    );
    expect(postRes.status).toBe(200);

    expect(calls).toEqual([
      { url: "https://control.modal.run/api/sandboxes/sb-1/t3-links?profile=work", method: "GET" },
      { url: "https://control.modal.run/api/sandboxes/sb-1/t3-links?profile=work", method: "POST" },
    ]);
  });
});
