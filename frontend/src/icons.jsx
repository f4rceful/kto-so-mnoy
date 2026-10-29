function Icon({ size = 24, stroke = 2, decorative = false, children }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={stroke}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={decorative ? 'true' : undefined}
    >
      {children}
    </svg>
  );
}

export const SearchIcon = () => <Icon><circle cx="11" cy="11" r="6" /><path d="m20 20-4.2-4.2" /></Icon>;
export const FilterIcon = () => <Icon><path d="M4 6h16" /><path d="M7 12h10" /><path d="M10 18h4" /></Icon>;
export const SortIcon = () => <Icon><path d="M8 5v14" /><path d="m4 15 4 4 4-4" /><path d="M16 19V5" /><path d="m12 9 4-4 4 4" /></Icon>;
export const SettingsIcon = () => <Icon><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></Icon>;
export const CloseIcon = () => <Icon><path d="M6 6l12 12" /><path d="M18 6 6 18" /></Icon>;
export const CheckIcon = () => <Icon><path d="m5 12.5 4.5 4.5L19 7.5" /></Icon>;
export const ChevronIcon = () => <Icon><path d="m9 6 6 6-6 6" /></Icon>;
export const BackIcon = () => <Icon><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></Icon>;
export const FeedIcon = () => <Icon><rect x="4" y="4" width="16" height="6" rx="2" /><rect x="4" y="14" width="16" height="6" rx="2" /></Icon>;
export const PlusIcon = () => <Icon><path d="M12 5v14" /><path d="M5 12h14" /></Icon>;
export const ProfileIcon = () => <Icon><circle cx="12" cy="8" r="4" /><path d="M4 20c1.5-4 4.5-6 8-6s6.5 2 8 6" /></Icon>;
export const ArrowUpIcon = () => <Icon><path d="M12 19V5" /><path d="m5 12 7-7 7 7" /></Icon>;

export const CalendarIcon = () => <Icon size={14} decorative><rect x="4" y="5" width="16" height="15" rx="3" /><path d="M8 3v4M16 3v4M4 10h16" /></Icon>;
export const PencilIcon = () => <Icon size={14} decorative><path d="M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></Icon>;
export const PinIcon = () => <Icon size={16} decorative><path d="M12 21s-6-5.2-6-10a6 6 0 0 1 12 0c0 4.8-6 10-6 10Z" /><circle cx="12" cy="11" r="2" /></Icon>;
export const GlobeIcon = () => <Icon size={16} decorative><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3Z" /></Icon>;
export const FlagIcon = () => <Icon size={16} decorative><path d="M5 21V4" /><path d="M5 4h11l-2 4 2 4H5" /></Icon>;
export const EyeOffIcon = () => <Icon size={16} decorative><path d="M3 3l18 18" /><path d="M10.6 6.2A9.6 9.6 0 0 1 12 6c5 0 8.5 4 9.5 6a12 12 0 0 1-2.6 3.3M6.6 7.6A12.5 12.5 0 0 0 2.5 12C3.5 14 7 18 12 18c1.4 0 2.6-.3 3.7-.8" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></Icon>;
export const SchoolIcon = () => <Icon size={16} decorative><path d="M3 10 12 5l9 5-9 5-9-5Z" /><path d="M7 12.5V17c0 1 2.2 2 5 2s5-1 5-2v-4.5" /></Icon>;
export const UsersIcon = () => <Icon size={16} decorative><circle cx="9" cy="8" r="3" /><path d="M3 19c.6-3.2 3-5 6-5s5.4 1.8 6 5" /><path d="M16 5.2a3 3 0 0 1 0 5.6M18 14.3c1.7.7 2.7 2.2 3 4.7" /></Icon>;
export const ShareIcon = () => <Icon size={22} decorative><path d="M12 15V4M8 8l4-4 4 4" /><path d="M5 12v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" /></Icon>;

export const AcceptIcon = () => <Icon size={18} stroke={2.4} decorative><path d="m5 12.5 4.5 4.5L19 7" /></Icon>;
export const DeclineIcon = () => <Icon size={18} stroke={2.4} decorative><path d="M6 6l12 12M18 6 6 18" /></Icon>;

export const UndoIcon = () => <Icon size={20}><path d="M9 14 4 9l5-5" /><path d="M4 9h9a6 6 0 0 1 0 12h-2" /></Icon>;
export const RedoIcon = () => <Icon size={20}><path d="m15 14 5-5-5-5" /><path d="M20 9h-9a6 6 0 0 0 0 12h2" /></Icon>;
export const BulletListIcon = () => <Icon size={20}><path d="M9 6h11M9 12h11M9 18h11" /><path d="M4 6h.01M4 12h.01M4 18h.01" strokeWidth="3" /></Icon>;
