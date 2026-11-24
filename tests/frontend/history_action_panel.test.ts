import assert from "node:assert/strict";
import test from "node:test";

import {
  historyDetailCloseEffect,
  historyManagementPanelHtml,
  historySelectionDetailResolution,
  historySelectionPanelHtml,
  nextHistoryActionPanelSection,
  shouldClearHistoryTaskFromBlankSurface,
  type HistoryActionPanelCopy,
} from "../../codex_image/webui/frontend/src/history-action-panel.ts";

const copy: HistoryActionPanelCopy = {
  libraryTitle: "History",
  libraryDescription: "Back up or restore history data.",
  backup: "Back up tasks",
  importBackup: "Import backup",
  selectTasks: "Select tasks",
  selectedCount: (count) => `${count} tasks selected`,
  exitSelection: "Exit bulk selection",
  organize: "Organize",
  favorite: "Favorite",
  unfavorite: "Unfavorite",
  addTag: "Add tag",
  removeTag: "Remove tag",
  archive: "Archive",
  restore: "Restore",
  export: "Export",
  imagesOnly: "Images only",
  imagesWithPrompts: "Images + prompts",
  confirmDelete: "Confirm delete",
  deleteTasks: "Delete",
  cancel: "Cancel",
  close: "Close",
};

test("management state exposes backup and import without task-detail placeholder copy", () => {
  const html = historyManagementPanelHtml(copy);
  assert.match(html, /data-history-detail-mode="management"/);
  assert.match(html, /data-history-open-backup/);
  assert.match(html, /data-history-open-import/);
  assert.match(html, /data-history-enter-selection-mode/);
  assert.doesNotMatch(html, /Select a historical task/);

  const selectingHtml = historyManagementPanelHtml(copy, { selectionMode: true });
  assert.match(selectingHtml, /data-history-exit-selection-mode/);
  assert.match(selectingHtml, /Exit bulk selection/);
  assert.match(selectingHtml, /aria-pressed="true"/);
});

test("selection state renders inline organize, export, backup, and separated danger actions", () => {
  const html = historySelectionPanelHtml({
    copy,
    count: 5,
    expandedSection: "organize",
    deleteConfirming: false,
  });
  assert.match(html, /5 tasks selected/);
  assert.match(html, /data-history-bulk-clear/);
  assert.match(html, /data-history-toggle-action-section="organize"[^>]*aria-expanded="true"/);
  assert.match(html, /data-history-bulk-favorite/);
  assert.match(html, /data-history-bulk-unfavorite/);
  assert.match(html, /data-history-open-tag-picker="add"/);
  assert.match(html, /data-history-open-tag-picker="remove"/);
  assert.match(html, /data-history-bulk-archive/);
  assert.match(html, /data-history-bulk-restore/);
  assert.match(html, /data-history-toggle-action-section="export"[^>]*aria-expanded="false"/);
  assert.match(html, /data-history-open-backup="selected"/);
  assert.match(html, /class="history-action-danger"/);
  assert.match(html, /data-history-bulk-delete/);
});

test("export expansion exposes both existing export modes and delete confirmation supplies cancel", () => {
  const exportHtml = historySelectionPanelHtml({
    copy,
    count: 2,
    expandedSection: "export",
    deleteConfirming: false,
  });
  assert.match(exportHtml, /data-history-export-mode="images_only"/);
  assert.match(exportHtml, /data-history-export-mode="images_with_prompts"/);

  const confirmHtml = historySelectionPanelHtml({
    copy,
    count: 2,
    expandedSection: "",
    deleteConfirming: true,
  });
  assert.match(confirmHtml, /Confirm delete/);
  assert.match(confirmHtml, /data-history-cancel-bulk-delete/);
});

test("only one inline section remains expanded", () => {
  assert.equal(nextHistoryActionPanelSection("", "organize"), "organize");
  assert.equal(nextHistoryActionPanelSection("organize", "export"), "export");
  assert.equal(nextHistoryActionPanelSection("export", "export"), "");
});

test("one selected task resolves to its detail while multiple tasks resolve to bulk actions", () => {
  assert.equal(historySelectionDetailResolution({
    selectedCount: 3,
    selectedTaskId: "task-a",
    detailTaskId: "task-a",
  }), "selection");
  assert.equal(historySelectionDetailResolution({
    selectedCount: 1,
    selectionMode: false,
    selectedTaskId: "task-a",
    detailTaskId: "task-a",
  }), "task");
  assert.equal(historySelectionDetailResolution({
    selectedCount: 0,
    selectedTaskId: "task-a",
    detailTaskId: "",
  }), "load-task");
  assert.equal(historySelectionDetailResolution({
    selectedCount: 0,
    selectedTaskId: "",
    detailTaskId: "",
  }), "management");
});

test("multi-select mode keeps one selected task in the bulk panel instead of opening its detail", () => {
  assert.equal(historySelectionDetailResolution({
    selectedCount: 1,
    selectionMode: true,
    selectedTaskId: "task-a",
    detailTaskId: "",
  }), "selection");
  assert.equal(historySelectionDetailResolution({
    selectedCount: 0,
    selectionMode: true,
    selectedTaskId: "",
    detailTaskId: "",
  }), "management");
});

test("closing a viewed task clears it even when the detail pane is a narrow drawer", () => {
  assert.equal(historyDetailCloseEffect({ narrow: true, mode: "task" }), "clear-task");
  assert.equal(historyDetailCloseEffect({ narrow: true, mode: "empty" }), "clear-task");
  assert.equal(historyDetailCloseEffect({ narrow: true, mode: "selection" }), "dismiss");
  assert.equal(historyDetailCloseEffect({ narrow: true, mode: "management" }), "dismiss");
});

test("only a plain primary click on the task-list blank surface clears unified single selection", () => {
  assert.equal(shouldClearHistoryTaskFromBlankSurface({
    detailMode: "task",
    selectedCount: 1,
    isTaskListBlankSurface: true,
    button: 0,
    hasModifier: false,
  }), true);

  assert.equal(shouldClearHistoryTaskFromBlankSurface({
    detailMode: "selection",
    selectedCount: 3,
    selectionMode: false,
    isTaskListBlankSurface: true,
    button: 0,
    hasModifier: false,
  }), true);

  assert.equal(shouldClearHistoryTaskFromBlankSurface({
    detailMode: "management",
    selectedCount: 0,
    selectionMode: true,
    isTaskListBlankSurface: true,
    button: 0,
    hasModifier: false,
  }), true);

  for (const override of [
    { detailMode: "management" as const },
    { isTaskListBlankSurface: false },
    { button: 1 },
    { hasModifier: true },
  ]) {
    assert.equal(shouldClearHistoryTaskFromBlankSurface({
      detailMode: "task",
      selectedCount: 1,
      selectionMode: false,
      isTaskListBlankSurface: true,
      button: 0,
      hasModifier: false,
      ...override,
    }), false);
  }
});
