const paths = {
  file: "M5 3h9l5 5v13H5z M14 3v6h5 M8 13h8 M8 17h6",
  clip: "M8 13l7-7a3 3 0 014 4L9 20a5 5 0 01-7-7L12 3 M5 15l9-9",
  link: "M10 14l4-4 M8 16l-1 1a4 4 0 01-6-6l5-5a4 4 0 016 0 M16 8l1-1a4 4 0 016 6l-5 5a4 4 0 01-6 0",
  chevron: "M7 10l5 5 5-5",
  user: "M16 7a4 4 0 11-8 0 4 4 0 018 0 M4 21v-3a8 8 0 0116 0v3z",
  warning: "M12 3L2 21h20z M12 9v5 M12 18h.01",
  copy: "M9 9h12v12H9z M5 16H2V2h14v3",
  folder: "M2 6V3h7l3 3h10v15H2z",
  database:
    "M3 6c0-5 18-5 18 0s-18 5-18 0 M3 6v12c0 5 18 5 18 0V6 M3 12c0 5 18 5 18 0",
  grid: "M3 3h6v6H3z M15 3h6v6h-6z M3 15h6v6H3z M15 15h6v6h-6z",
  source: "M4 4h16v16H4z M4 9h16 M9 9v11 M14 9v11 M4 14h16",
  mail: "M3 5h18v14H3z M3 6l9 7 9-7",
  check: "M5 12l4 4L19 6",
  shield: "M12 3l8 3v6c0 5-8 9-8 9s-8-4-8-9V6z M8 12l3 3 5-6",
  filter: "M3 4h18l-7 8v7l-4 2v-9z",
  clock: "M12 8v5l4 2 M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0",
  send: "M3 11L21 3l-8 18-3-8z M10 13L21 3",
  stop: "M8 3h8l5 5v8l-5 5H8l-5-5V8z M9 9h6v6H9z",
  reply: "M9 5l-6 6 6 6 M3 11h10c5 0 8 3 8 8",
  branch:
    "M6 5v14 M6 12h7c4 0 5-3 5-7 M6 12h7c4 0 5 3 5 7 M3 3h6v4H3z M15 3h6v4h-6z M15 17h6v4h-6z",
  search: "M10 3a7 7 0 1 1 0 14 7 7 0 0 1 0-14 M15 15l6 6",
  refresh: "M20 8a8 8 0 1 0 0 8 M20 3v5h-5",
  plus: "M12 5v14 M5 12h14",
  arrow: "M5 12h14 M14 7l5 5-5 5",
  book: "M3 4l9 2 9-2v16l-9 2-9-2z M12 6v16",
  fit: "M3 9V3h6 M15 3h6v6 M21 15v6h-6 M9 21H3v-6",
  close: "M6 6l12 12 M18 6L6 18",
  trash: "M4 7h16 M9 7V4h6v3 M7 7l1 14h8l1-14 M10 11v6 M14 11v6",
};
export type IconName = keyof typeof paths;

export default function Icon({
  name,
  size = 20,
}: {
  name: IconName;
  size?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.grid} />
    </svg>
  );
}
