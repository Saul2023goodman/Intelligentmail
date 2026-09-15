import type { SVGProps } from 'react'

/* One icon family, one stroke weight (1.6), one 20×20 grid.
   Filled and outline styles are never mixed at the same hierarchy level. */

type IconProps = SVGProps<SVGSVGElement> & { size?: number }

function Svg({ size = 16, children, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...rest}
    >
      {children}
    </svg>
  )
}

export const Icon = {
  grid: (p: IconProps) => (
    <Svg {...p}>
      <rect x="2.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="11.5" y="2.5" width="6" height="6" rx="1" />
      <rect x="2.5" y="11.5" width="6" height="6" rx="1" />
      <rect x="11.5" y="11.5" width="6" height="6" rx="1" />
    </Svg>
  ),
  stack: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 2.6 17.4 6.4 10 10.2 2.6 6.4Z" />
      <path d="M2.6 10.2 10 14l7.4-3.8" />
      <path d="M2.6 13.8 10 17.6l7.4-3.8" />
    </Svg>
  ),
  compose: (p: IconProps) => (
    <Svg {...p}>
      <path d="M13.4 3.2 16.8 6.6 7.4 16H4v-3.4Z" />
      <path d="M11.8 4.8 15.2 8.2" />
    </Svg>
  ),
  clock: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="7.2" />
      <path d="M10 5.8V10l2.8 1.8" />
    </Svg>
  ),
  play: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="7.2" />
      <path d="M8.3 7.1 13.2 10l-4.9 2.9Z" />
    </Svg>
  ),
  inbox: (p: IconProps) => (
    <Svg {...p}>
      <path d="M2.8 11.6 5.1 4.3a1.4 1.4 0 0 1 1.3-.9h7.2a1.4 1.4 0 0 1 1.3.9l2.3 7.3" />
      <path d="M2.8 11.6h4l1 2.2h4.4l1-2.2h4v3.2a1.8 1.8 0 0 1-1.8 1.8H4.6a1.8 1.8 0 0 1-1.8-1.8Z" />
    </Svg>
  ),
  reply: (p: IconProps) => (
    <Svg {...p}>
      <path d="M7.6 4.4 3.2 8.8l4.4 4.4" />
      <path d="M3.2 8.8h7.6a5.6 5.6 0 0 1 5.6 5.6v1.2" />
    </Svg>
  ),
  chart: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3 16.8h14" />
      <path d="M5.4 16.8V10M9.4 16.8V5.4M13.4 16.8v-4.6" />
    </Svg>
  ),
  sliders: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3.4 6.2h13.2M3.4 13.8h13.2" />
      <circle cx="7.6" cy="6.2" r="2" />
      <circle cx="12.8" cy="13.8" r="2" />
    </Svg>
  ),
  search: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="9" cy="9" r="5.6" />
      <path d="M13.2 13.2 17 17" />
    </Svg>
  ),
  plus: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 4.2v11.6M4.2 10h11.6" />
    </Svg>
  ),
  chevronDown: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5.4 7.8 10 12.4l4.6-4.6" />
    </Svg>
  ),
  chevronRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="M7.8 5.4 12.4 10l-4.6 4.6" />
    </Svg>
  ),
  chevronLeft: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12.2 5.4 7.6 10l4.6 4.6" />
    </Svg>
  ),
  close: (p: IconProps) => (
    <Svg {...p}>
      <path d="M5.2 5.2 14.8 14.8M14.8 5.2 5.2 14.8" />
    </Svg>
  ),
  check: (p: IconProps) => (
    <Svg {...p} strokeWidth={2.4}>
      <path d="M4.4 10.6 8.1 14.3 15.6 6.2" />
    </Svg>
  ),
  sync: (p: IconProps) => (
    <Svg {...p}>
      <path d="M16.4 8.6A6.6 6.6 0 0 0 4.6 5.8" />
      <path d="M3.6 11.4a6.6 6.6 0 0 0 11.8 2.8" />
      <path d="M4.2 2.8v3.2h3.2M15.8 17.2V14h-3.2" />
    </Svg>
  ),
  alert: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 3.4 17.6 16.6H2.4Z" />
      <path d="M10 8.2v3.6M10 14.2v.1" />
    </Svg>
  ),
  lock: (p: IconProps) => (
    <Svg {...p}>
      <rect x="4.2" y="8.8" width="11.6" height="7.8" rx="1.6" />
      <path d="M6.8 8.8V6.4a3.2 3.2 0 0 1 6.4 0v2.4" />
    </Svg>
  ),
  diamond: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 2.8 17.2 10 10 17.2 2.8 10Z" />
    </Svg>
  ),
  paperclip: (p: IconProps) => (
    <Svg {...p}>
      <path d="M14.6 9.2 9.4 14.4a3.2 3.2 0 0 1-4.5-4.5l6-6a2.2 2.2 0 0 1 3.1 3.1l-6 6a1.2 1.2 0 0 1-1.7-1.7l5.4-5.4" />
    </Svg>
  ),
  shield: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 2.6 16 5v5c0 3.6-2.5 6.3-6 7.4-3.5-1.1-6-3.8-6-7.4V5Z" />
      <path d="M7.6 10.1 9.3 11.8l3.3-3.4" />
    </Svg>
  ),
  layers: (p: IconProps) => (
    <Svg {...p}>
      <path d="M10 2.8 17 6.4 10 10 3 6.4Z" />
      <path d="M3 13.6 10 17.2l7-3.6" />
    </Svg>
  ),
  arrowRight: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3.8 10h12.4M11.8 5.6 16.2 10l-4.4 4.4" />
    </Svg>
  ),
  panel: (p: IconProps) => (
    <Svg {...p}>
      <rect x="2.6" y="3.4" width="14.8" height="13.2" rx="1.8" />
      <path d="M12.4 3.4v13.2" />
    </Svg>
  ),
  rows: (p: IconProps) => (
    <Svg {...p}>
      <rect x="2.6" y="3.6" width="14.8" height="12.8" rx="1.6" />
      <path d="M2.6 8h14.8M2.6 12.2h14.8M7.4 8v8.4" />
    </Svg>
  ),
  command: (p: IconProps) => (
    <Svg {...p}>
      <path d="M6.6 3.6a1.9 1.9 0 1 0 0 3.8h6.8a1.9 1.9 0 1 0 0-3.8v12.8a1.9 1.9 0 1 0 0-3.8H6.6a1.9 1.9 0 1 0 0 3.8Z" />
    </Svg>
  ),
  enter: (p: IconProps) => (
    <Svg {...p}>
      <path d="M16 4.6v5.2a2 2 0 0 1-2 2H4.4" />
      <path d="M7.6 8.4 4.2 11.8l3.4 3.4" />
    </Svg>
  ),
  eye: (p: IconProps) => (
    <Svg {...p}>
      <path d="M1.8 10S4.8 4.8 10 4.8 18.2 10 18.2 10 15.2 15.2 10 15.2 1.8 10 1.8 10Z" />
      <circle cx="10" cy="10" r="2.4" />
    </Svg>
  ),
  file: (p: IconProps) => (
    <Svg {...p}>
      <path d="M11.4 2.8H5.6a1.6 1.6 0 0 0-1.6 1.6v11.2a1.6 1.6 0 0 0 1.6 1.6h8.8a1.6 1.6 0 0 0 1.6-1.6V7.4Z" />
      <path d="M11.4 2.8v4.6H16" />
    </Svg>
  ),
  history: (p: IconProps) => (
    <Svg {...p}>
      <path d="M3.4 10a6.6 6.6 0 1 0 2-4.7" />
      <path d="M3.2 3.6v3.6h3.6" />
      <path d="M10 6.8V10l2.4 1.6" />
    </Svg>
  ),
  compass: (p: IconProps) => (
    <Svg {...p}>
      <circle cx="10" cy="10" r="7.2" />
      <path d="M12.8 7.2 11.4 11.4 7.2 12.8 8.6 8.6Z" />
    </Svg>
  ),
  collapse: (p: IconProps) => (
    <Svg {...p}>
      <path d="M12.6 4.6 7.4 10l5.2 5.4" />
      <path d="M4 4v12" />
    </Svg>
  ),
}

export type IconName = keyof typeof Icon
