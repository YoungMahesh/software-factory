import { getCaCertificate, ensureTlsCertificates } from "@/services/certs";

export async function GET() {
  await ensureTlsCertificates().catch(() => {});
  const pem = getCaCertificate();
  return new Response(pem, {
    status: 200,
    headers: {
      "Content-Type": "application/x-x509-ca-cert",
      "Content-Disposition": "inline; filename=\"ca.crt\"",
    },
  });
}
