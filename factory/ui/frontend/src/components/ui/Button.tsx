import React from "react";
import { Loader2 } from "lucide-react";

export type ButtonVariant =
  | "primary"
  | "secondary"
  | "danger"
  | "ghost"
  | "pill-outline"
  | "inverted"
  | "success";
export type ButtonSize = "sm" | "md";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  icon?: React.ReactNode;
  inverted?: boolean;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "bg-primary hover:bg-cohere-black text-white rounded-pill shadow-sm disabled:bg-primary/50",
  inverted:
    "bg-white hover:bg-soft-stone text-primary rounded-pill shadow-sm disabled:opacity-50",
  secondary:
    "bg-transparent text-ink underline underline-offset-4 hover:text-black font-medium disabled:opacity-50",
  danger:
    "bg-transparent hover:bg-coral/10 text-coral border border-coral rounded-pill font-medium disabled:opacity-50",
  ghost:
    "bg-transparent hover:bg-soft-stone text-muted hover:text-ink rounded-pill transition-colors disabled:opacity-50",
  "pill-outline":
    "bg-transparent hover:bg-soft-stone/70 text-primary border border-hairline rounded-pill font-medium disabled:opacity-50",
  success:
    "bg-pale-green border border-deep-green/30 text-deep-green rounded-pill font-medium disabled:opacity-50",
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: "px-3 py-1 text-xs rounded-pill",
  md: "px-4 py-2 text-xs rounded-pill",
};

export const Button: React.FC<ButtonProps> = ({
  variant = "primary",
  size = "md",
  isLoading = false,
  icon,
  children,
  className = "",
  disabled,
  inverted,
  ...props
}) => {
  const isButtonDisabled = disabled || isLoading;
  const isExplicitInverted =
    (inverted && variant === "primary") ||
    variant === "inverted" ||
    (variant === "primary" && className.includes("bg-white") && className.includes("text-primary"));
  const effectiveVariant = isExplicitInverted ? "inverted" : variant;
  const baseVariant = variantClasses[effectiveVariant];

  return (
    <button
      {...props}
      disabled={isButtonDisabled}
      className={`inline-flex items-center justify-center space-x-1.5 font-semibold transition-colors disabled:opacity-50 disabled:pointer-events-none cursor-pointer ${baseVariant} ${sizeClasses[size]} ${className}`}
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
