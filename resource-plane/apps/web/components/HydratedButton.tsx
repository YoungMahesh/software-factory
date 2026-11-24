import type React from "react";
import { useHydrated } from "../lib/useHydrated";

export interface HydratedButtonProps
	extends React.ButtonHTMLAttributes<HTMLButtonElement> {
	children?: React.ReactNode;
	connectingTitle?: string;
	isHydrated?: boolean;
}

export function HydratedButton({
	disabled,
	title,
	className = "",
	children,
	connectingTitle = "Connecting to Control Plane...",
	type = "button",
	isHydrated: propIsHydrated,
	...props
}: HydratedButtonProps) {
	const hookIsHydrated = useHydrated();
	const isHydrated = propIsHydrated ?? hookIsHydrated;
	const isDisabled = Boolean(disabled || !isHydrated);
	const resolvedTitle = !isHydrated ? connectingTitle : title;

	return (
		<button
			type={type}
			{...props}
			disabled={isDisabled}
			title={resolvedTitle}
			className={`${className} ${
				!isHydrated
					? "opacity-75 cursor-wait transition-opacity"
					: "cursor-pointer"
			}`}
		>
			{children}
		</button>
	);
}

export default HydratedButton;
