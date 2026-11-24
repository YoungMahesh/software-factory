import { useHydrated } from "../lib/useHydrated";

export interface HydrationProgressBarProps {
	isHydrated?: boolean;
}

export function HydrationProgressBar({
	isHydrated: propIsHydrated,
}: HydrationProgressBarProps = {}) {
	const hookIsHydrated = useHydrated();
	const isHydrated = propIsHydrated ?? hookIsHydrated;

	return (
		<div
			data-testid="hydration-progress-bar"
			aria-hidden={isHydrated}
			className={`fixed top-0 left-0 right-0 z-[9999] h-[2px] pointer-events-none transition-opacity duration-500 overflow-hidden ${
				isHydrated ? "opacity-0" : "opacity-100"
			}`}
		>
			<div className="h-full w-full bg-[#00e599] shadow-[0_0_8px_#00e599] animate-indeterminate-bar" />
		</div>
	);
}
