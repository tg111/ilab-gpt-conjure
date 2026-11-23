import { updateExecutionSummary } from "./execution-summary";

/** Refresh the execution summary shown under the composer. */
export function updateRequestPreview(): void {
  updateExecutionSummary();
}
