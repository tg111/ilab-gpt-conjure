import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { getLegacyBridge } from "./state";

interface AppVersionPayload {
  current_version_label?: string;
}

let appVersionInitialized = false;
let payload: AppVersionPayload | null = null;

function renderAppVersion(): void {
  const versionLabel = getLegacyBridge().els.versionLabel as HTMLElement | null;
  if (!versionLabel) return;
  const currentLabel = payload?.current_version_label;
  versionLabel.textContent = currentLabel
    ? formatTranslation("footer.version", { version: currentLabel })
    : translate("footer.versionLoading");
}

async function refreshAppVersion(): Promise<void> {
  try {
    const response = await fetch("/api/app-version");
    if (!response.ok) throw new Error(`Version API failed: ${response.status}`);
    payload = await response.json();
  } catch {
    payload = null;
  }
  renderAppVersion();
}

export function initAppVersionFeature(): void {
  if (appVersionInitialized) return;
  appVersionInitialized = true;
  document.addEventListener(LOCALE_CHANGE_EVENT, () => renderAppVersion());
  renderAppVersion();
  void refreshAppVersion();
}
