/**
 * Desktop "studio" shell: the top bar's few controls move into the sidebar
 * footer so results get its height, the sidebar starts narrower, and Ctrl+B
 * collapses it. Controls are moved, never recreated; leaving the desktop width
 * puts everything back.
 */
import { LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { STUDIO_QUERY } from "./studio-composer";

const COLLAPSED_STORAGE_KEY = "codex-image-studio-sidebar-collapsed";
// Owned by shell-ui.ts; present only once the user has dragged the sidebar.
const SIDEBAR_WIDTH_STORAGE_KEY = "codex-image-sidebar-width";
const STUDIO_SIDEBAR_WIDTH = "280px";
const SIDEBAR_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="16" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9 4v16" stroke="currentColor" stroke-width="2"/></svg>';

function readStorage(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    // Storage disabled: the choice lasts for this page only.
  }
}

function sidebarButton(className: string): HTMLButtonElement {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.setAttribute("aria-controls", "sidebar");
  button.innerHTML = SIDEBAR_ICON;
  return button;
}

export function initStudioShell(): void {
  const sidebar = document.getElementById("sidebar");
  const footer = sidebar?.querySelector<HTMLElement>(".sidebar-footer");
  const mainWrapper = document.querySelector<HTMLElement>(".main-wrapper");
  if (!sidebar || !footer || !mainWrapper) return;
  const query = window.matchMedia(STUDIO_QUERY);

  const tools = document.createElement("div");
  tools.className = "studio-sidebar-tools";
  const toolRow = document.createElement("div");
  toolRow.className = "studio-sidebar-tool-row";
  tools.append(toolRow);

  const collapseButton = sidebarButton("ghost-button studio-sidebar-collapse");
  const expandButton = sidebarButton("ghost-button studio-sidebar-expand");

  const origins = new Map<HTMLElement, Comment>();
  const move = (id: string, target: HTMLElement) => {
    const node = document.getElementById(id);
    if (!node) return;
    const marker = document.createComment(`studio-${id}`);
    node.before(marker);
    origins.set(node, marker);
    target.append(node);
  };

  let active = false;
  let ownsWidth = false;

  const label = () => {
    const shortcut = /Mac|iPhone|iPad/.test(navigator.platform) ? "⌘B" : "Ctrl+B";
    collapseButton.title = `${translate("studio.collapseSidebar")} (${shortcut})`;
    collapseButton.setAttribute("aria-label", translate("studio.collapseSidebar"));
    expandButton.title = `${translate("studio.expandSidebar")} (${shortcut})`;
    expandButton.setAttribute("aria-label", translate("studio.expandSidebar"));
  };

  const setCollapsed = (collapsed: boolean, persist = true) => {
    document.body.toggleAttribute("data-studio-sidebar-collapsed", collapsed);
    collapseButton.setAttribute("aria-expanded", String(!collapsed));
    expandButton.setAttribute("aria-expanded", String(!collapsed));
    if (persist) writeStorage(COLLAPSED_STORAGE_KEY, collapsed ? "1" : null);
  };

  const apply = () => {
    const next = query.matches;
    if (next === active) return;
    active = next;
    if (active) {
      footer.prepend(tools);
      move("queueButton", toolRow);
      move("taskNotificationButton", toolRow);
      move("generationProviderSettingsButton", toolRow);
      toolRow.append(collapseButton);
      move("themeSwitcher", tools);
      move("taskNotificationCenter", tools);
      mainWrapper.prepend(expandButton);
      // Narrower default; a width the user dragged to is left alone.
      if (!readStorage(SIDEBAR_WIDTH_STORAGE_KEY) && !sidebar.style.getPropertyValue("--sidebar-width")) {
        sidebar.style.setProperty("--sidebar-width", STUDIO_SIDEBAR_WIDTH);
        ownsWidth = true;
      }
      setCollapsed(readStorage(COLLAPSED_STORAGE_KEY) === "1", false);
      label();
    } else {
      origins.forEach((marker, node) => marker.replaceWith(node));
      origins.clear();
      tools.remove();
      collapseButton.remove();
      expandButton.remove();
      if (ownsWidth && !readStorage(SIDEBAR_WIDTH_STORAGE_KEY)
        && sidebar.style.getPropertyValue("--sidebar-width") === STUDIO_SIDEBAR_WIDTH) {
        sidebar.style.removeProperty("--sidebar-width");
      }
      ownsWidth = false;
      document.body.removeAttribute("data-studio-sidebar-collapsed");
    }
  };

  const toggle = () => setCollapsed(!document.body.hasAttribute("data-studio-sidebar-collapsed"));
  collapseButton.addEventListener("click", toggle);
  expandButton.addEventListener("click", toggle);
  document.addEventListener("keydown", (event) => {
    if (!active) return;
    const mac = /Mac|iPhone|iPad/.test(navigator.platform);
    const modifier = mac ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
    if (modifier && !event.altKey && !event.shiftKey && event.key.toLowerCase() === "b") {
      // Also keeps the prompt editor from applying bold formatting.
      event.preventDefault();
      toggle();
    }
  }, true);
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    if (active) label();
  });
  query.addEventListener("change", apply);
  apply();
}
