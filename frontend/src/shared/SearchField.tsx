import type { ReactNode } from "react";
import Icon from "./Icon";

export default function SearchField({
  label,
  value,
  onChange,
  placeholder,
  iconSize = 17,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
  iconSize?: number;
  children?: ReactNode;
}) {
  return (
    <label className="search">
      <Icon name="search" size={iconSize} />
      <input
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
      />
      {children}
    </label>
  );
}
