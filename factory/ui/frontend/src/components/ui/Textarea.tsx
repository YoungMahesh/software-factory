import React from "react";

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean;
}

export const Textarea: React.FC<TextareaProps> = ({
  className = "",
  error = false,
  ...props
}) => {
  return (
    <textarea
      {...props}
      className={`w-full bg-white border ${
        error
          ? "border-error focus:border-error focus:ring-error/20"
          : "border-hairline focus:border-form-focus focus:ring-form-focus"
      } rounded-xl px-3.5 py-2.5 text-xs text-ink placeholder-muted focus:outline-none focus:ring-1 resize-none disabled:opacity-50 transition-colors ${className}`}
    />
  );
};
