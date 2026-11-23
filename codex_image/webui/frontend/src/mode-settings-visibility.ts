import type { CatalogProviderBinding } from "./types";

export interface ModeSettingsVisibility {
  showMainModel: boolean;
}

/**
 * The main model belongs to Responses protocols. The catalog says which
 * bindings use one; without a catalog binding, the direct Images API does not.
 */
export function resolveModeSettingsVisibility(
  binding: Pick<CatalogProviderBinding, "protocol_profile" | "capabilities"> | null,
  legacyDirectApi: boolean,
): ModeSettingsVisibility {
  if (!binding) return { showMainModel: !legacyDirectApi };
  return {
    showMainModel: binding.capabilities
      ? binding.capabilities.uses_main_model
      : binding.protocol_profile.endsWith("_responses"),
  };
}
