import React from "react";
import { ShieldCheck, Download, Copy, Check } from "lucide-react";
import { HydratedButton } from "./HydratedButton";

export interface CaCertificateSectionProps {
	onCopyPem?: () => void;
	copied?: boolean;
	isHydrated?: boolean;
}

export function CaCertificateSection({
	onCopyPem,
	copied,
	isHydrated,
}: CaCertificateSectionProps) {
	return (
		<div
			data-testid="ca-certificate-section"
			className="rounded-xl border border-[var(--line)] bg-[var(--foam)] p-3.5"
		>
			<div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
				<div className="flex items-center gap-2.5">
					<div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[rgba(0,229,153,0.12)] text-[#009b67] dark:text-[#00e599]">
						<ShieldCheck className="h-4 w-4" />
					</div>
					<div>
						<h4 className="text-xs font-bold uppercase tracking-wider text-[var(--sea-ink)] m-0">
							Root CA Certificate
						</h4>
						<p className="text-xs text-[var(--sea-ink-soft)] m-0 mt-0.5">
							Required for TLS certificate and hostname verification (
							<code className="font-mono text-[11px]">sslmode=verify-full</code>
							).
						</p>
					</div>
				</div>

				<div className="flex items-center gap-2 shrink-0">
					<a
						href="/api/ca.crt"
						download="ca.crt"
						className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] hover:text-[#00e599] transition no-underline shadow-xs cursor-pointer"
					>
						<Download className="h-3.5 w-3.5 text-[#00e599]" />
						<span>Download ca.crt</span>
					</a>
					<HydratedButton
						type="button"
						onClick={onCopyPem}
						isHydrated={isHydrated}
						className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-1.5 text-xs font-semibold text-[var(--sea-ink)] hover:bg-[var(--chip-bg)] transition shadow-xs"
					>
						{copied ? (
							<>
								<Check className="h-3.5 w-3.5 text-[#00e599]" />
								<span>Copied!</span>
							</>
						) : (
							<>
								<Copy className="h-3.5 w-3.5" />
								<span>Copy PEM</span>
							</>
						)}
					</HydratedButton>
				</div>
			</div>
		</div>
	);
}
export default CaCertificateSection;
