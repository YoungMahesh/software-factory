import React from "react";

export type BadgeVariant =
  | "stage"
  | "status"
  | "success"
  | "danger"
  | "warning"
  | "neutral";

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const variantClasses: Record<BadgeVariant, string> = {
  stage:
    "px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-indigo-950 text-indigo-300 uppercase border border-indigo-800",
  status:
    "px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-slate-900 text-slate-300 border border-slate-800",
  success:
    "px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-800",
  danger:
    "px-2 py-0.5 rounded text-[10px] font-medium bg-rose-950/80 text-rose-300 border border-rose-800",
  warning:
    "px-2 py-0.5 rounded text-[10px] font-medium bg-amber-950/80 text-amber-300 border border-amber-800",
  neutral:
    "px-2 py-0.5 rounded text-[10px] font-medium bg-slate-800 text-slate-300 border border-slate-700",
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
