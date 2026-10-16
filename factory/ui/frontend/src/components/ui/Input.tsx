import React from "react";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}

export const Input: React.FC<InputProps> = ({
  className = "",
  error = false,
  ...props
}) => {
  return (
    <input
      {...props}
      className={`w-full bg-white border ${
        error
          ? "border-error focus:border-error focus:ring-error/20"
          : "border-hairline focus:border-form-focus focus:ring-form-focus"
      } rounded-lg px-3 py-2 text-xs text-ink placeholder-muted focus:outline-none focus:ring-1 transition-colors disabled:opacity-50 ${className}`}
    />
  );
};
