import React from "react";

export type BadgeVariant =
  | "stage"
  | "status"
  | "success"
  | "danger"
  | "warning"
  | "neutral"
  | "coral"
  | "console";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantClasses: Record<BadgeVariant, string> = {
  stage:
    "px-2.5 py-0.5 rounded text-[10px] font-mono font-bold bg-primary text-white uppercase border border-hairline/40 tracking-wider",
  status:
    "px-2 py-0.5 rounded text-[10px] font-mono font-medium bg-soft-stone text-ink border border-hairline",
  success:
    "px-2.5 py-0.5 rounded-pill text-[10px] font-medium bg-pale-green text-deep-green border border-deep-green/20",
  danger:
    "px-2.5 py-0.5 rounded-pill text-[10px] font-medium bg-coral/10 text-coral border border-coral/30",
  warning:
    "px-2.5 py-0.5 rounded-pill text-[10px] font-medium bg-amber-50 text-amber-700 border border-amber-200",
  neutral:
    "px-2 py-0.5 rounded-pill text-[10px] font-medium bg-soft-stone text-ink border border-hairline",
  coral:
    "px-2.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase bg-coral/10 text-coral border border-coral/30",
  console:
    "px-2.5 py-0.5 rounded text-[10px] font-mono font-semibold uppercase bg-primary text-slate-200 border border-white/10",
};

export const Badge: React.FC<BadgeProps> = ({
  variant = "neutral",
  children,
  className = "",
  ...props
}) => {
  return (
    <span
      {...props}
      className={`inline-flex items-center space-x-1 shrink-0 ${variantClasses[variant]} ${className}`}
    >
      {children}
    </span>
  );
};
