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
      className={`w-full bg-slate-950 border ${
        error ? "border-rose-800 focus:ring-rose-500" : "border-slate-800 focus:ring-indigo-500"
      } rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 transition-colors disabled:opacity-50 ${className}`}
    />
  );
};
