export type HistoryActionPanelSection = "" | "organize" | "export";
export type HistoryDetailMode = "empty" | "management" | "selection" | "task";
export type HistorySelectionDetailResolution = "selection" | "task" | "load-task" | "management";

export function historySelectionDetailResolution({
  selectedCount,
  selectionMode = false,
  selectedTaskId,
  detailTaskId,
}: {
  selectedCount: number;
  selectionMode?: boolean;
  selectedTaskId: string;
  detailTaskId: string;
}): HistorySelectionDetailResolution {
  if (selectedCount > 1) return "selection";
  // Multi-select mode never opens a task detail: on narrow screens that drawer would cover the grid.
  if (selectionMode && selectedCount === 1) return "selection";
  if (!selectedTaskId) return "management";
  return detailTaskId === selectedTaskId ? "task" : "load-task";
}

export function historyDetailCloseEffect({
  mode,
}: {
  narrow: boolean;
  mode: HistoryDetailMode;
}): "clear-task" | "dismiss" {
  return mode === "task" || mode === "empty" ? "clear-task" : "dismiss";
}

export function shouldClearHistoryTaskFromBlankSurface({
  detailMode,
  selectedCount,
  selectionMode,
  isTaskListBlankSurface,
  button,
  hasModifier,
}: {
  detailMode: HistoryDetailMode;
  selectedCount: number;
  selectionMode: boolean;
  isTaskListBlankSurface: boolean;
  button: number;
  hasModifier: boolean;
}): boolean {
  const hasSelection = (detailMode === "task" && selectedCount === 1)
    || (detailMode === "selection" && selectedCount > 1)
    || selectionMode;
  return hasSelection
    && isTaskListBlankSurface
    && button === 0
    && !hasModifier;
}

export type HistoryActionPanelCopy = {
  libraryTitle: string;
  libraryDescription: string;
  backup: string;
  importBackup: string;
  selectTasks: string;
  selectedCount: (count: number) => string;
  exitSelection: string;
  organize: string;
  favorite: string;
  unfavorite: string;
  addTag: string;
  removeTag: string;
  archive: string;
  restore: string;
  export: string;
  imagesOnly: string;
  imagesWithPrompts: string;
  confirmDelete: string;
  deleteTasks: string;
  cancel: string;
  close: string;
};

type SelectionPanelOptions = {
  copy: HistoryActionPanelCopy;
  count: number;
  expandedSection: HistoryActionPanelSection;
  deleteConfirming: boolean;
};

const ICONS = {
  archive: '<path d="M4 8h16v12H4zM3 4h18v4H3z"/><path d="M9 12h6"/>',
  backup: '<path d="M4 8h16v12H4zM3 4h18v4H3zM12 11v6m0 0-3-3m3 3 3-3"/>',
  chevron: '<path d="m8 10 4 4 4-4"/>',
  close: '<path d="M7 7 17 17M17 7 7 17"/>',
  delete: '<path d="M5 7h14M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5"/>',
  export: '<path d="M12 3v11m0 0 4-4m-4 4-4-4M5 17v3h14v-3"/>',
  favorite: '<path d="m12 3 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
  image: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m5 16 4-4 3 3 2-2 5 4M16.5 9h.01"/>',
  import: '<path d="M4 8h16v12H4zM3 4h18v4H3zM12 17v-6m0 0-3 3m3-3 3 3"/>',
  organize: '<path d="M4 7h16M7 12h10M9 17h6"/>',
  restore: '<path d="M4 8h16v12H4zM3 4h18v4H3z"/><path d="M12 17v-6m0 0-3 3m3-3 3 3"/>',
  select: '<path d="M5 6h14M5 12h14M5 18h14"/><path d="m3 6 .8.8L5.4 5m-2.4 7 .8.8 1.6-1.8m-2.4 7 .8.8 1.6-1.8"/>',
  tag: '<path d="M4 5h7l9 9-6 6-9-9z"/><circle cx="8.5" cy="8.5" r="1"/>',
} as const;

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function icon(name: keyof typeof ICONS, className = "history-action-icon"): string {
  return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${ICONS[name]}</svg>`;
}

function drawerClose(copy: HistoryActionPanelCopy): string {
  return `
    <button class="ghost-button drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml(copy.close)}">
      ${icon("close", "drawer-close-icon")}
    </button>`;
}

export function nextHistoryActionPanelSection(
  current: HistoryActionPanelSection,
  requested: Exclude<HistoryActionPanelSection, "">,
): HistoryActionPanelSection {
  return current === requested ? "" : requested;
}

export function historyManagementPanelHtml(
  copy: HistoryActionPanelCopy,
  { selectionMode = false }: { selectionMode?: boolean } = {},
): string {
  const selectionAttribute = selectionMode
    ? "data-history-exit-selection-mode"
    : "data-history-enter-selection-mode";
  const selectionLabel = selectionMode ? copy.exitSelection : copy.selectTasks;
  return `
    <div class="history-action-panel" data-history-detail-mode="management">
      <div class="history-detail-header history-action-panel-header">
        <div>
          <h2 class="history-detail-title" tabindex="-1">${escapeHtml(copy.libraryTitle)}</h2>
        </div>
        ${drawerClose(copy)}
      </div>
      <p class="history-action-panel-description">${escapeHtml(copy.libraryDescription)}</p>
      <div class="history-action-list">
        <button class="history-action-row${selectionMode ? " history-action-row-primary" : ""}" type="button" ${selectionAttribute} aria-pressed="${selectionMode}">
          ${icon("select")}
          <span>${escapeHtml(selectionLabel)}</span>
          ${icon("chevron", "history-action-row-arrow")}
        </button>
        <button class="history-action-row history-action-row-primary" type="button" data-history-open-backup>
          ${icon("backup")}
          <span>${escapeHtml(copy.backup)}</span>
          ${icon("chevron", "history-action-row-arrow")}
        </button>
        <button class="history-action-row" type="button" data-history-open-import>
          ${icon("import")}
          <span>${escapeHtml(copy.importBackup)}</span>
          ${icon("chevron", "history-action-row-arrow")}
        </button>
      </div>
    </div>`;
}

export function historySelectionPanelHtml({
  copy,
  count,
  expandedSection,
  deleteConfirming,
}: SelectionPanelOptions): string {
  const organizeOpen = expandedSection === "organize";
  const exportOpen = expandedSection === "export";
  return `
    <div class="history-action-panel" data-history-detail-mode="selection">
      <div class="history-detail-header history-action-panel-header">
        <div>
          <h2 class="history-detail-title" tabindex="-1">${escapeHtml(copy.selectedCount(count))}</h2>
        </div>
        <div class="history-action-panel-header-actions">
          <button class="history-action-clear" type="button" data-history-bulk-clear>${escapeHtml(copy.exitSelection)}</button>
          ${drawerClose(copy)}
        </div>
      </div>
      <div class="history-action-list">
        <button class="history-action-row history-action-disclosure" type="button" data-history-toggle-action-section="organize" aria-expanded="${organizeOpen}">
          ${icon("organize")}
          <span>${escapeHtml(copy.organize)}</span>
          ${icon("chevron", "history-action-row-chevron")}
        </button>
        ${organizeOpen ? `
          <div class="history-action-options history-action-options-organize" data-history-action-section="organize">
            <button type="button" data-history-bulk-favorite>${icon("favorite")}<span>${escapeHtml(copy.favorite)}</span></button>
            <button type="button" data-history-bulk-unfavorite>${icon("favorite")}<span>${escapeHtml(copy.unfavorite)}</span></button>
            <button type="button" data-history-open-tag-picker="add">${icon("tag")}<span>${escapeHtml(copy.addTag)}</span></button>
            <button type="button" data-history-open-tag-picker="remove">${icon("tag")}<span>${escapeHtml(copy.removeTag)}</span></button>
            <button type="button" data-history-bulk-archive>${icon("archive")}<span>${escapeHtml(copy.archive)}</span></button>
            <button type="button" data-history-bulk-restore>${icon("restore")}<span>${escapeHtml(copy.restore)}</span></button>
          </div>` : ""}
        <button class="history-action-row history-action-disclosure" type="button" data-history-toggle-action-section="export" aria-expanded="${exportOpen}">
          ${icon("export")}
          <span>${escapeHtml(copy.export)}</span>
          ${icon("chevron", "history-action-row-chevron")}
        </button>
        ${exportOpen ? `
          <div class="history-action-options history-action-options-export" data-history-action-section="export">
            <button type="button" data-history-export-mode="images_only">${icon("image")}<span>${escapeHtml(copy.imagesOnly)}</span></button>
            <button type="button" data-history-export-mode="images_with_prompts">${icon("export")}<span>${escapeHtml(copy.imagesWithPrompts)}</span></button>
            <p class="history-action-status" data-history-action-export-status aria-live="polite"></p>
          </div>` : ""}
        <button class="history-action-row history-action-row-primary" type="button" data-history-open-backup="selected">
          ${icon("backup")}
          <span>${escapeHtml(copy.backup)}</span>
          ${icon("chevron", "history-action-row-arrow")}
        </button>
      </div>
      <div class="history-action-danger">
        <button class="history-action-row history-action-row-danger" type="button" data-history-bulk-delete>
          ${icon("delete")}
          <span>${escapeHtml(deleteConfirming ? copy.confirmDelete : copy.deleteTasks)}</span>
        </button>
        ${deleteConfirming ? `<button class="history-action-cancel" type="button" data-history-cancel-bulk-delete>${escapeHtml(copy.cancel)}</button>` : ""}
      </div>
    </div>`;
}
