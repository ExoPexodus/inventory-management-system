export interface TimezoneOption {
  value: string;
  label: string;
  region: string;
}

export const TIMEZONE_OPTIONS: TimezoneOption[] = [
  // India
  { value: "Asia/Kolkata", label: "India (IST, UTC+5:30)", region: "Asia" },
  // Indonesia
  { value: "Asia/Jakarta", label: "Indonesia West (WIB, UTC+7)", region: "Asia" },
  { value: "Asia/Makassar", label: "Indonesia Central (WITA, UTC+8)", region: "Asia" },
  { value: "Asia/Jayapura", label: "Indonesia East (WIT, UTC+9)", region: "Asia" },
  // Canada
  { value: "America/Vancouver", label: "Canada Pacific (PT)", region: "Americas" },
  { value: "America/Edmonton", label: "Canada Mountain (MT)", region: "Americas" },
  { value: "America/Winnipeg", label: "Canada Central (CT)", region: "Americas" },
  { value: "America/Toronto", label: "Canada Eastern (ET)", region: "Americas" },
  { value: "America/Halifax", label: "Canada Atlantic (AT)", region: "Americas" },
  { value: "America/St_Johns", label: "Canada Newfoundland (NT, UTC-3:30)", region: "Americas" },
  // Other major zones
  { value: "UTC", label: "UTC", region: "UTC" },
  { value: "Europe/London", label: "UK (GMT/BST)", region: "Europe" },
  { value: "Europe/Paris", label: "Central Europe (CET/CEST, UTC+1/+2)", region: "Europe" },
  { value: "Europe/Istanbul", label: "Turkey (TRT, UTC+3)", region: "Europe" },
  { value: "Asia/Dubai", label: "UAE / Gulf (GST, UTC+4)", region: "Asia" },
  { value: "Asia/Karachi", label: "Pakistan (PKT, UTC+5)", region: "Asia" },
  { value: "Asia/Dhaka", label: "Bangladesh (BST, UTC+6)", region: "Asia" },
  { value: "Asia/Bangkok", label: "Thailand / Vietnam (ICT, UTC+7)", region: "Asia" },
  { value: "Asia/Singapore", label: "Singapore / Malaysia (SGT, UTC+8)", region: "Asia" },
  { value: "Asia/Shanghai", label: "China (CST, UTC+8)", region: "Asia" },
  { value: "Asia/Tokyo", label: "Japan (JST, UTC+9)", region: "Asia" },
  { value: "Australia/Sydney", label: "Australia East (AEST/AEDT)", region: "Pacific" },
  { value: "Pacific/Auckland", label: "New Zealand (NZST/NZDT)", region: "Pacific" },
  { value: "America/New_York", label: "US Eastern (ET)", region: "Americas" },
  { value: "America/Chicago", label: "US Central (CT)", region: "Americas" },
  { value: "America/Denver", label: "US Mountain (MT)", region: "Americas" },
  { value: "America/Los_Angeles", label: "US Pacific (PT)", region: "Americas" },
  { value: "America/Sao_Paulo", label: "Brazil (BRT, UTC-3)", region: "Americas" },
  { value: "Africa/Cairo", label: "Egypt (EET, UTC+2)", region: "Africa" },
  { value: "Africa/Lagos", label: "Nigeria / West Africa (WAT, UTC+1)", region: "Africa" },
  { value: "Africa/Nairobi", label: "Kenya / East Africa (EAT, UTC+3)", region: "Africa" },
];

export const MONTH_OPTIONS = [
  { value: 1, label: "January" },
  { value: 2, label: "February" },
  { value: 3, label: "March" },
  { value: 4, label: "April" },
  { value: 5, label: "May" },
  { value: 6, label: "June" },
  { value: 7, label: "July" },
  { value: 8, label: "August" },
  { value: 9, label: "September" },
  { value: 10, label: "October" },
  { value: 11, label: "November" },
  { value: 12, label: "December" },
];
