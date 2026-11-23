import { readFileSync } from "node:fs";

import { activeParameterValuesFor } from "../../codex_image/webui/frontend/src/model-parameters";

const fixturePath = process.env.GENERATION_CATALOG_FIXTURE;
if (!fixturePath) throw new Error("GENERATION_CATALOG_FIXTURE is required");
const catalog = JSON.parse(readFileSync(fixturePath, "utf8"));
const result: Record<string, Record<string, unknown>> = {};
for (const modelId of ["nano-banana-pro"]) {
  const model = catalog.models.find((item: any) => item.id === modelId);
  result[modelId] = activeParameterValuesFor(model, "generate", {});
}
process.stdout.write(JSON.stringify(result));
