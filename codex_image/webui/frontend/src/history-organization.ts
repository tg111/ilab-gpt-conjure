export type HistoryTag = {
  tag_id: string;
  name: string;
  count?: number;
};

export type HistoryOrganization = {
  favorite: boolean;
  tags: HistoryTag[];
};

export type HistoryOrganizationFilters = {
  favorite: boolean;
  tagIds: string[];
  untagged: boolean;
};

export type OrganizeHistoryTasksChange = {
  task_ids: string[];
  favorite?: boolean | null;
  add_tag_ids?: string[];
  remove_tag_ids?: string[];
};

export class HistoryOrganizationRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "HistoryOrganizationRequestError";
    this.status = status;
  }
}

type EscapeHtml = (value: unknown) => string;
type HistoryTagPickerCreateLabels = {
  placeholder: string;
  submitLabel: string;
};

function uniqueNonempty(values: Iterable<unknown>): string[] {
  return [
    ...new Set(
      [...values]
        .map((value) => String(value ?? "").trim())
        .filter(Boolean),
    ),
  ];
}

export function readHistoryOrganizationFilters(
  params: URLSearchParams,
): HistoryOrganizationFilters {
  const tagIds = uniqueNonempty(params.getAll("tag"));
  const untagged =
    params.get("untagged") === "true" && tagIds.length === 0;
  return {
    favorite: params.get("favorite") === "true",
    tagIds,
    untagged,
  };
}

export function appendHistoryOrganizationQuery(
  params: URLSearchParams,
  filters: HistoryOrganizationFilters,
): void {
  if (filters.favorite) {
    params.set("favorite", "true");
  }
  if (filters.untagged) {
    params.set("untagged", "true");
    return;
  }
  for (const tagId of uniqueNonempty(filters.tagIds)) {
    params.append("tag", tagId);
  }
}

export function writeHistoryOrganizationFilters(
  params: URLSearchParams,
  filters: HistoryOrganizationFilters,
): void {
  params.delete("favorite");
  params.delete("tag");
  params.delete("untagged");
  appendHistoryOrganizationQuery(params, filters);
}

export function withHistoryTagFilter(
  filters: HistoryOrganizationFilters,
  tagId: string,
  selected: boolean,
): HistoryOrganizationFilters {
  const cleanTagId = String(tagId ?? "").trim();
  const tagIds = new Set(uniqueNonempty(filters.tagIds));
  if (cleanTagId) {
    if (selected) tagIds.add(cleanTagId);
    else tagIds.delete(cleanTagId);
  }
  return {
    favorite: filters.favorite,
    tagIds: [...tagIds],
    untagged: selected ? false : filters.untagged,
  };
}

export function withHistoryUntaggedFilter(
  filters: HistoryOrganizationFilters,
  selected: boolean,
): HistoryOrganizationFilters {
  return {
    favorite: filters.favorite,
    tagIds: selected ? [] : [...filters.tagIds],
    untagged: selected,
  };
}

export function taskMatchesHistoryOrganizationFilters(
  organization: HistoryOrganization,
  filters: HistoryOrganizationFilters,
): boolean {
  if (filters.favorite && !organization.favorite) return false;
  const taskTagIds = new Set(
    organization.tags.map((tag) => tag.tag_id),
  );
  if (
    filters.tagIds.some((tagId) => !taskTagIds.has(tagId))
  ) {
    return false;
  }
  if (filters.untagged && taskTagIds.size > 0) return false;
  return true;
}

export function historyOrganizationSummarySupported(
  value: unknown,
): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const summary = value as Record<string, unknown>;
  return (
    typeof summary.favorite_total === "number" &&
    Number.isFinite(summary.favorite_total) &&
    typeof summary.untagged_total === "number" &&
    Number.isFinite(summary.untagged_total) &&
    Array.isArray(summary.tags)
  );
}

export function historyTaskRowsSupportOrganization(
  rows: unknown,
): boolean {
  return (
    Array.isArray(rows) &&
    rows.every(
      (row) =>
        Boolean(row) &&
        typeof row === "object" &&
        !Array.isArray(row) &&
        typeof (row as Record<string, unknown>).favorite ===
          "boolean" &&
        Array.isArray(
          (row as Record<string, unknown>).tags,
        ),
    )
  );
}

async function historyOrganizationRequest<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
      ...(init?.headers || {}),
    },
  });
  const payload = await response
    .json()
    .catch(() => ({})) as Record<string, unknown>;
  if (!response.ok) {
    const rawDetail = payload.detail;
    const detail =
      typeof rawDetail === "string"
        ? rawDetail
        : rawDetail &&
            typeof rawDetail === "object" &&
            "message" in rawDetail
          ? String(
              (rawDetail as Record<string, unknown>).message,
            )
          : `HTTP ${response.status}`;
    throw new HistoryOrganizationRequestError(
      response.status,
      detail,
    );
  }
  return payload as T;
}

export async function createHistoryTag(
  name: string,
): Promise<HistoryTag> {
  const payload = await historyOrganizationRequest<{
    tag: HistoryTag;
  }>("/api/task-history/tags", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
  return payload.tag;
}

export async function renameHistoryTag(
  tagId: string,
  name: string,
): Promise<HistoryTag> {
  const payload = await historyOrganizationRequest<{
    tag: HistoryTag;
  }>(
    `/api/task-history/tags/${encodeURIComponent(tagId)}`,
    {
      method: "PATCH",
      body: JSON.stringify({ name }),
    },
  );
  return payload.tag;
}

export async function deleteHistoryTag(
  tagId: string,
): Promise<{
  deleted: string;
  affected_task_count: number;
}> {
  return historyOrganizationRequest(
    `/api/task-history/tags/${encodeURIComponent(tagId)}`,
    { method: "DELETE" },
  );
}

export async function organizeHistoryTasks(
  change: OrganizeHistoryTasksChange,
): Promise<Record<string, HistoryOrganization>> {
  const payload = await historyOrganizationRequest<{
    organizations: Record<string, HistoryOrganization>;
  }>("/api/task-history/organize", {
    method: "POST",
    body: JSON.stringify({
      task_ids: uniqueNonempty(change.task_ids),
      favorite: change.favorite ?? null,
      add_tag_ids: uniqueNonempty(change.add_tag_ids || []),
      remove_tag_ids: uniqueNonempty(
        change.remove_tag_ids || [],
      ),
    }),
  });
  return payload.organizations || {};
}

export async function createHistoryTagForTasks(
  name: string,
  taskIds: Iterable<unknown>,
): Promise<{
  tag: HistoryTag;
  organizations: Record<string, HistoryOrganization>;
}> {
  const tag = await createHistoryTag(name);
  const cleanTaskIds = uniqueNonempty(taskIds);
  const organizations = cleanTaskIds.length
    ? await organizeHistoryTasks({
        task_ids: cleanTaskIds,
        add_tag_ids: [tag.tag_id],
      })
    : {};
  return { tag, organizations };
}

export function historyTagPickerCreateHtml(
  escapeHtml: EscapeHtml,
  labels: HistoryTagPickerCreateLabels,
): string {
  return `
    <div class="history-tag-picker-create">
      <form
        class="history-tag-picker-create-form"
        data-history-tag-create-inline
      >
        <input
          class="control"
          type="text"
          maxlength="40"
          autocomplete="off"
          data-history-tag-create-name
          placeholder="${escapeHtml(labels.placeholder)}"
          aria-label="${escapeHtml(labels.placeholder)}"
        />
        <button
          class="ghost-button text-sm"
          type="submit"
          data-history-tag-create-submit
        >${escapeHtml(labels.submitLabel)}</button>
      </form>
      <div
        class="history-tag-picker-create-status"
        data-history-tag-create-status
        role="status"
      ></div>
    </div>
  `;
}

export function historyFavoriteButtonHtml(
  taskId: string,
  favorite: boolean,
  escapeHtml: EscapeHtml,
  label: string,
): string {
  return `
    <button
      class="history-favorite-button${favorite ? " active" : ""}"
      type="button"
      data-history-favorite-task="${escapeHtml(taskId)}"
      aria-pressed="${favorite ? "true" : "false"}"
      aria-label="${escapeHtml(label)}"
      title="${escapeHtml(label)}"
    >
      <svg class="history-favorite-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M12 3.7l2.5 5.1 5.6.8-4.1 4 1 5.6-5-2.6-5 2.6 1-5.6-4.1-4 5.6-.8L12 3.7Z" />
      </svg>
    </button>
  `;
}

export function historyCardTagsHtml(
  tags: HistoryTag[],
  escapeHtml: EscapeHtml,
): string {
  const visible = tags.slice(0, 2);
  const remainder = Math.max(0, tags.length - visible.length);
  if (!visible.length) return "";
  return `
    <div class="history-card-tags">
      ${visible
        .map(
          (tag) => `
            <span
              class="history-tag-chip"
              data-history-tag-id="${escapeHtml(tag.tag_id)}"
            >${escapeHtml(tag.name)}</span>
          `,
        )
        .join("")}
      ${
        remainder
          ? `<span class="history-tag-more">+${remainder}</span>`
          : ""
      }
    </div>
  `;
}

export function historyDetailTagsHtml(
  tags: HistoryTag[],
  escapeHtml: EscapeHtml,
): string {
  return tags
    .map(
      (tag) => `
        <span
          class="history-tag-chip"
          data-history-tag-id="${escapeHtml(tag.tag_id)}"
        >${escapeHtml(tag.name)}</span>
      `,
    )
    .join("");
}

export function historyTagPickerHtml(
  tags: HistoryTag[],
  selectedTagIds: Iterable<string>,
  escapeHtml: EscapeHtml,
): string {
  const selected = new Set(selectedTagIds);
  return tags
    .map((tag) => {
      const checked = selected.has(tag.tag_id);
      return `
        <label class="history-tag-picker-option">
          <input
            type="checkbox"
            value="${escapeHtml(tag.tag_id)}"
            ${checked ? "checked" : ""}
          />
          <span>${escapeHtml(tag.name)}</span>
        </label>
      `;
    })
    .join("");
}
