import React from "react";
import { Loader2 } from "lucide-react";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  icon?: React.ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm disabled:bg-indigo-600/50",
  secondary:
    "bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 shadow-sm",
  danger:
    "bg-rose-600 hover:bg-rose-500 text-white shadow-sm disabled:bg-rose-600/50",
  ghost:
    "text-slate-400 hover:text-slate-200 hover:bg-slate-800 bg-transparent",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-2.5 py-1.5 text-xs rounded-lg",
  md: "px-4 py-2 text-xs rounded-lg",
};

export const Button: React.FC<ButtonProps> = ({
  variant = "primary",
  size = "md",
  isLoading = false,
  icon,
  children,
  className = "",
  disabled,
  ...props
}) => {
  const isButtonDisabled = disabled || isLoading;

  return (
    <button
      {...props}
      disabled={isButtonDisabled}
      className={`inline-flex items-center justify-center space-x-1.5 font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none cursor-pointer ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
    >
      {isLoading ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
      ) : (
        icon && <span className="shrink-0">{icon}</span>
      )}
      {children && <span>{children}</span>}
    </button>
  );
};
