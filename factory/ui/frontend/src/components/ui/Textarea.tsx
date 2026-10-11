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
      className={`w-full bg-slate-950 border ${
        error ? "border-rose-800 focus:ring-rose-500" : "border-slate-800 focus:ring-indigo-500"
      } rounded-xl px-3.5 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 resize-none disabled:opacity-50 transition-colors ${className}`}
    />
  );
};
