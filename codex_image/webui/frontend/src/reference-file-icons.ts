export type ReferenceFileIconFamily =
  | "pdf" | "spreadsheet" | "document" | "presentation"
  | "code" | "data" | "mail";

export type ReferenceFileIconSpec = {
  readonly extension: string;
  readonly label: string;
  readonly family: ReferenceFileIconFamily;
  readonly color: string;
};

const FAMILY_EXTENSIONS: Record<ReferenceFileIconFamily, readonly string[]> = {
  pdf: ["pdf"],
  spreadsheet: ["xla", "xlb", "xlc", "xlm", "xls", "xlt", "xlw", "xlsx", "csv", "tsv", "iif"],
  document: ["doc", "docx", "dot", "odt", "rtf", "wiz"],
  presentation: ["pot", "ppa", "pps", "ppt", "pwz", "pptx"],
  code: ["asm", "bat", "c", "cc", "conf", "cpp", "css", "cxx", "def", "h", "hh", "in", "js", "mjs", "pl", "py", "s", "sql"],
  data: ["dic", "htm", "html", "json", "ksh", "list", "log", "markdown", "md", "mht", "mhtml", "mime", "nws", "rst", "srt", "text", "txt", "vtt", "xml"],
  mail: ["eml", "ics", "ifb", "vcf"],
};

const FAMILY_COLORS: Record<ReferenceFileIconFamily, string> = {
  pdf: "#d37a70", spreadsheet: "#64a982", document: "#6e9cc7",
  presentation: "#c79862", code: "#9385c9", data: "#6fa4a2", mail: "#879993",
};

const LABEL_OVERRIDES: Record<string, string> = {
  markdown: "MKDN",
  mhtml: "MHTL",
};

const ICON_SPECS: ReadonlyMap<string, ReferenceFileIconSpec> = new Map(
  Object.entries(FAMILY_EXTENSIONS).flatMap(([family, extensions]) =>
    extensions.map((extension) => [extension, Object.freeze({
      extension,
      label: LABEL_OVERRIDES[extension] || extension.toUpperCase(),
      family: family as ReferenceFileIconFamily,
      color: FAMILY_COLORS[family as ReferenceFileIconFamily],
    })] as const),
  ),
);

const FALLBACK_SPEC: ReferenceFileIconSpec = Object.freeze({
  extension: "", label: "FILE", family: "mail", color: "#879993",
});

export function referenceFileExtension(filename: unknown): string {
  const value = String(filename || "");
  const separator = value.lastIndexOf(".");
  return separator >= 0 ? value.slice(separator + 1).toLowerCase() : "";
}

export function referenceFileIconSpec(filename: unknown): ReferenceFileIconSpec {
  return ICON_SPECS.get(referenceFileExtension(filename)) || FALLBACK_SPEC;
}

export function referenceFileIconSvgMarkup(filename: unknown): string {
  const spec = referenceFileIconSpec(filename);
  const fontSize = spec.label.length > 3 ? 4.5 : 5.3;
  return `<svg class="reference-file-format-icon" viewBox="0 0 24 28" aria-hidden="true" focusable="false" style="color:${spec.color}">
    <rect x="3" y="2" width="18" height="24" rx="4" fill="currentColor" fill-opacity=".14" stroke="currentColor" stroke-opacity=".62"></rect>
    <path d="M3 6a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4" fill="currentColor"></path>
    <text x="12" y="17" text-anchor="middle" fill="currentColor" font-size="${fontSize}" font-weight="800" font-family="Arial, sans-serif">${spec.label}</text>
  </svg>`;
}
