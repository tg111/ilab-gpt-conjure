/** Real controls and editor with synthetic local images; never calls a provider. */
import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";
const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const failures: any[] = [], errors: string[] = [];
let assertions = 0;
const pause = (ms = 100) => new Promise(resolve => setTimeout(resolve, ms));
function check(name: string, pass: boolean, detail?: unknown) { assertions++; if (!pass) failures.push({ name, detail }); }

async function run() {
  await prepareFixtureOrigin(); localStorage.clear();
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const w = frame.contentWindow!, d = frame.contentDocument!;
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => d.querySelector<T>(selector)!;
  const until = async (predicate: () => boolean) => { const end = Date.now() + 15000; while (!predicate()) { if (Date.now() > end) throw new Error("initialization timed out"); await pause(); } };
  await until(() => !!w.__codexImageWebUI?.state.generationCatalog);
  const { state, methods } = w.__codexImageWebUI!;
  state.generationCatalog.providers.push({ id: "qa-image26", name: "Synthetic Image 2.6", builtin: false, available: true, bindings: [{
    id: "image26", canonical_model_id: "gpt-image-2.6-flare", remote_model_id: "gpt-image-2.6-flare",
    protocol_profile: "openai_images", parameter_codec: "gpt_openai_images", operations: ["generate", "edit"],
  }] });
  methods.selectConcreteModel("gpt-image-2.6-flare");
  methods.selectGenerationProvider("qa-image26");
  const input = (selector: string, value: string) => { const e = find<HTMLInputElement>(selector); e.value = value; e.dispatchEvent(new w.Event("input", {bubbles: true})); e.dispatchEvent(new w.Event("change", {bubbles: true})); };
  const params = () => methods.currentCanonicalParameters();
  // Controls are rendered from the catalog; address them by parameter id.
  // Collapsed advanced options (GIF timing, compression) open from the output header on desktop.
  const field = (id: string) => d.querySelector<HTMLElement>(`:is(#modelParameterGrid, #modelAdvancedSlot) [data-parameter-id="${id}"]`);
  const choice = (id: string, value: string) => field(id)?.querySelector<HTMLButtonElement>(`[data-val="${value}"]`) || null;
  const choose = (id: string, value: string) => { const button = choice(id, value); if (!button) throw new Error(`missing ${id}=${value}`); button.click(); };
  const numberInput = (id: string) => field(id)!.querySelector<HTMLInputElement>('input[type="number"]')!;
  const setNumber = async (id: string, value: string) => { const e = numberInput(id); e.value = value; e.dispatchEvent(new w.Event("input", {bubbles: true})); await pause(0); };
  const fieldError = (id: string) => field(id)?.querySelector<HTMLElement>(".model-parameter-error:not(.hidden)")?.textContent || "";
  const customInputs = () => [...field("canvas.size")!.querySelectorAll<HTMLInputElement>(".pixel-size-input")];
  const setCustomSize = async (width: string, height: string) => {
    const [widthInput, heightInput] = customInputs();
    widthInput.value = width; widthInput.dispatchEvent(new w.Event("input", {bubbles: true}));
    heightInput.value = height; heightInput.dispatchEvent(new w.Event("input", {bubbles: true}));
    await pause(0);
  };
  const blocked = () => Object.keys(state.parameterValidationErrorsByModel?.[state.selectedModelId] || {});
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const [width, height] of [[1512, 773], [1280, 699], [375, 812]]) {
      frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause(250);
      if (d.body.classList.contains("mobile-ui")) { find(".mobile-parameters-button").click(); await pause(); }
      const name = `${theme} ${width}x${height}`;
      choose("output.format", "gif"); await setNumber("gpt.frame_count", "12"); await setNumber("gpt.frame_duration_ms", "100");
      choose("gpt.quality", "max"); choose("gpt.complexity", "low");
      check(`${name}: GIF timing fields appear`, !!field("gpt.frame_count") && !!field("gpt.frame_duration_ms"));
      if (!d.body.classList.contains("mobile-ui")) {
        const advanced = find<HTMLDetailsElement>("#modelAdvancedSlot > details"), trigger = advanced.querySelector<HTMLElement>("summary")!;
        trigger.click(); await pause();
        const box = advanced.querySelector(".model-parameter-advanced-grid")!.getBoundingClientRect();
        check(`${name}: advanced options open from the header`, advanced.open && advanced.contains(field("gpt.frame_count")));
        check(`${name}: advanced popover contained`, box.left >= 0 && box.right <= w.innerWidth && box.top >= 0 && box.bottom <= w.innerHeight, box.toJSON());
        numberInput("gpt.frame_count").focus();
        numberInput("gpt.frame_count").dispatchEvent(new w.KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
        check(`${name}: Escape closes advanced options and returns focus`, !advanced.open && d.activeElement === trigger);
      }
      check(`${name}: no irrelevant controls`, !field("gpt.output_compression") && !!choice("gpt.background", "transparent")?.disabled);
      check(`${name}: canonical request`, params()["gpt.complexity"] === "low" && params()["gpt.quality"] === "max" && params()["gpt.frame_count"] === 12 && !("gpt.output_compression" in params()), params());
      const grid = find("#modelParameterGrid");
      check(`${name}: no panel horizontal overflow`, grid.scrollWidth <= grid.clientWidth + 1, { scroll: grid.scrollWidth, client: grid.clientWidth });
      choose("output.format", "png"); check(`${name}: animation fields omitted for PNG`, !("gpt.frame_count" in params()) && !field("gpt.frame_count"));
      choose("output.format", "gif"); check(`${name}: GIF values retained`, params()["gpt.frame_count"] === 12 && params()["gpt.frame_duration_ms"] === 100);
      if (d.body.classList.contains("mobile-ui")) find("#mobileParameters .drawer-close-button").click();
    }
  }
  frame.style.width = "1280px"; frame.style.height = "800px"; await pause(250);
  const lockedParams = params();
  find('#outputSettingsLockButton').click(); find('#outputSettingsLockButton').click();
  check("unlock preserves complexity and GIF timing", JSON.stringify(params()) === JSON.stringify(lockedParams), params());
  find('#outputSettingsLockButton').click();
  state.parameterDraftsByModel[state.selectedModelId] = { ...state.parameterDraftsByModel[state.selectedModelId], "gpt.frame_count": 2, "gpt.frame_duration_ms": 200, "gpt.complexity": "high" };
  methods.restoreOutputSettingsLock();
  check("persisted lock restores complexity and GIF timing", JSON.stringify(params()) === JSON.stringify(lockedParams), params());
  find('#outputSettingsLockButton').click();
  const historical = { ...state.tasks[0], summary_only: false, mode: 'generate', prompt: 'Synthetic GIF history', input_sources: [], local_input_files: [], reference_files: [], generation_snapshot: {
    canonical_model_id: 'gpt-image-2.6-flare', provider_id: 'qa-image26', protocol_profile: 'openai_images',
    // Stored with the earlier single size field; adoption upgrades it.
    requested_parameters: { ...lockedParams, 'canvas.mode': undefined, 'canvas.aspect_ratio': undefined, 'canvas.resolution': undefined, 'canvas.size': '512x512' },
  } };
  for (const key of ['canvas.mode', 'canvas.aspect_ratio', 'canvas.resolution']) delete historical.generation_snapshot.requested_parameters[key];
  state.tasks[0] = historical;
  methods.selectConcreteModel('gpt-image-2');
  const olderParams = params();
  await methods.selectTask(historical.task_id);
  check("cross-version history opens the inspector", !find('#taskParameterInspector').classList.contains('hidden'));
  check("cross-version history preserves current request until adoption", JSON.stringify(params()) === JSON.stringify(olderParams));
  find('#taskParameterInspector .task-parameter-adopt').click(); await pause(0);
  check("adoption selects the compatible historical model", state.selectedModelId === 'gpt-image-2.6-flare' && state.selectedProviderId === 'qa-image26');
  check("adoption preserves GIF format, dimensions and timing", params()['output.format'] === 'gif' && params()['canvas.mode'] === 'custom' && params()['canvas.size'] === '512x512' && params()['gpt.frame_count'] === 12 && params()['gpt.frame_duration_ms'] === 100 && params()['gpt.complexity'] === 'low', params());
  check("a small GIF canvas is accepted", customInputs().map(item => item.value).join("x") === "512x512" && !blocked().includes("canvas.size"), blocked());
  await setNumber("gpt.frame_count", "64");
  check("small GIF canvas allows 64 frames", params()["gpt.frame_count"] === 64 && !fieldError("gpt.frame_count"), { max: numberInput("gpt.frame_count").max });
  await setCustomSize("3840", "3840");
  check("GIF frame limit follows canvas pixel budget", numberInput("gpt.frame_count").max === "9" && !!fieldError("gpt.frame_count") && blocked().includes("gpt.frame_count"), { max: numberInput("gpt.frame_count").max, blocked: blocked() });
  check("invalid GIF frame count remains editable", numberInput("gpt.frame_count").value === "64");
  await setNumber("gpt.frame_count", "9");
  check("GIF frame limit accepts a corrected value", !fieldError("gpt.frame_count") && !blocked().includes("gpt.frame_count"));
  choose("canvas.mode", "preset"); await pause(0); await setNumber("gpt.frame_count", "12");
  check("preset sizes keep the frame range", !fieldError("gpt.frame_count") && params()["gpt.frame_count"] === 12);
  const canvas = d.createElement("canvas"); canvas.width = 8192; canvas.height = 512;
  const ctx = canvas.getContext("2d")!; ctx.fillStyle = "#457b66"; ctx.fillRect(0, 0, 8192, 512);
  const blob = await new Promise<Blob>(resolve => canvas.toBlob(value => resolve(value!), "image/png"));
  const file = new w.File([blob], "synthetic.png", { type: "image/png" });
  methods.addImageFiles([file]); await pause();
  check("upload switches to edit without losing GIF or timing", state.mode === "edit" && params()["output.format"] === "gif" && params()["gpt.frame_count"] === 12 && params()["gpt.frame_duration_ms"] === 100, params());
  const relay = state.generationCatalog.providers.find((provider: any) => provider.id === "qa-image26");
  state.generationCatalog.providers.push({ ...relay, id: "qa-openai", name: "Synthetic OpenAI", gif_edit_max_frames: 16 });
  await setNumber("gpt.frame_count", "17");
  methods.selectGenerationProvider("qa-openai"); await pause(0);
  check("official reference GIF caps frames at 16 without changing the draft", numberInput("gpt.frame_count").max === "16" && numberInput("gpt.frame_count").value === "17" && !!fieldError("gpt.frame_count"));
  methods.selectGenerationProvider("qa-image26"); await pause(0);
  check("switching back to a relay restores its wider frame range", Number(numberInput("gpt.frame_count").max) > 16 && numberInput("gpt.frame_count").value === "17" && !fieldError("gpt.frame_count"));
  await setNumber("gpt.frame_count", "12");
  for (const theme of ["light", "dark"]) {
    find(`[data-theme-option="${theme}"]`).click();
    for (const [width, height] of [[1280, 800], [375, 812]]) {
      frame.style.width = `${width}px`; frame.style.height = `${height}px`; await pause(250);
      if (d.body.classList.contains("mobile-ui")) { find(".mobile-parameters-button").click(); await pause(); }
      const name = `reference GIF ${theme} ${width}x${height}`;
      check(`${name}: GIF and SVG enabled`, ["gif", "svg"].every(value => choice("output.format", value) && !choice("output.format", value)!.disabled));
      choose("output.format", "png");
      check(`${name}: PNG omits animation fields`, !("gpt.frame_count" in params()) && !("gpt.frame_duration_ms" in params()));
      const gif = choice("output.format", "gif")!;
      gif.focus(); check(`${name}: keyboard reaches GIF`, d.activeElement === gif && !gif.disabled);
      gif.click(); await pause(0);
      check(`${name}: selection restores timing`, params()["output.format"] === "gif" && params()["gpt.frame_count"] === 12 && params()["gpt.frame_duration_ms"] === 100, params());
      await setNumber("gpt.frame_count", "8"); await setNumber("gpt.frame_duration_ms", "150");
      check(`${name}: edits reach canonical parameters`, params()["gpt.frame_count"] === 8 && params()["gpt.frame_duration_ms"] === 150 && !("gpt.output_compression" in params()) && !!choice("gpt.background", "transparent")?.disabled, params());
      await setNumber("gpt.frame_count", "12"); await setNumber("gpt.frame_duration_ms", "100");
      choose("output.format", "svg"); await pause(0);
      check(`${name}: SVG omits GIF timing and compression`, !("gpt.frame_count" in params()) && !("gpt.frame_duration_ms" in params()) && !("gpt.output_compression" in params()) && !field("gpt.frame_count") && !field("gpt.output_compression"), params());
      check(`${name}: SVG allows a transparent background`, !choice("gpt.background", "transparent")?.disabled);
      choose("output.format", "gif"); await pause(0);
      check(`${name}: returning from SVG restores GIF timing`, params()["gpt.frame_count"] === 12 && params()["gpt.frame_duration_ms"] === 100, params());
      if (d.body.classList.contains("mobile-ui")) find("#mobileParameters .drawer-close-button").click();
    }
  }
  frame.style.width = "1280px"; frame.style.height = "800px"; await pause(250);
  methods.setMode("generate"); choose("output.format", "svg");
  const previousImageCount = state.images.length;
  methods.addImageFiles([new w.File([blob], "svg-reference.png", { type: "image/png" })]); await pause();
  check("upload preserves SVG when switching to edit", state.mode === "edit" && state.images.length === previousImageCount + 1 && params()["output.format"] === "svg", params());
  choose("output.format", "gif");
  const original = state.images[0].file;
  await methods.openImageEditor(0);
  find('[data-image-editor-mode="markup"]').click(); await pause();
  check("markup mode keeps image geometry fixed", find("#imageEditorModal").classList.contains("markup-mode") && w.getComputedStyle(find('[data-image-editor-tool="crop"]')).display === "none");
  const surface = find("#imageEditorKonvaMount .konvajs-content"); const rect = surface.getBoundingClientRect();
  const draw = (type: string, x: number) => surface.dispatchEvent(new w.PointerEvent(type, {bubbles: true, pointerId: 7, button: 0, buttons: type === "pointerup" ? 0 : 1, clientX: rect.left + rect.width * x, clientY: rect.top + rect.height * .5 }));
  draw("pointerdown", .25); draw("pointermove", .75); draw("pointerup", .75); await pause();
  const mount = find('#imageEditorKonvaMount');
  find('#imageEditorUndo').click();
  check("markup undo preserves original wide coordinates", mount.style.getPropertyValue('--image-editor-stage-raw-width') === '8192px' && find<HTMLCanvasElement>('#imageEditorCanvas').width === 8192);
  find('#imageEditorRedo').click();
  check("markup redo preserves original wide coordinates", mount.style.getPropertyValue('--image-editor-stage-raw-width') === '8192px' && find<HTMLCanvasElement>('#imageEditorCanvas').width === 8192);
  find("#imageEditorSave").click(); await until(() => find("#imageEditorModal").classList.contains("hidden"));
  check("markup preserves base file", state.images[0].file === original);
  const markup = state.images[0].markupFile;
  check("markup saved as separate PNG", !!markup && markup.type === "image/png");
  if (markup) {
    const bitmap = await w.createImageBitmap(markup); const layer = d.createElement("canvas"); layer.width = bitmap.width; layer.height = bitmap.height;
    const layerCtx = layer.getContext("2d")!; layerCtx.drawImage(bitmap, 0, 0); bitmap.close();
    const pixels = layerCtx.getImageData(0, 0, layer.width, layer.height).data;
    check("markup has matching dimensions and transparent background", layer.width === 8192 && layer.height === 512 && pixels.some((v, i) => i % 4 === 3 && v === 0) && pixels.some((v, i) => i % 4 === 3 && v > 0));
    await methods.openImageEditor(0); await pause();
    check("saved markup reopens in markup mode", find("#imageEditorModal").classList.contains("markup-mode"));
    check("reopened markup retains original wide coordinates", mount.style.getPropertyValue('--image-editor-stage-raw-width') === '8192px');
    find("#imageEditorClose").click();
  }
  methods.selectConcreteModel("gpt-image-2"); await pause(0);
  check("Image 2 keeps its original controls", !field("gpt.complexity") && !!field("gpt.quality") && !choice("gpt.quality", "max") && !!field("output.format"));
  check("Image 2 still excludes SVG and GIF", params()["output.format"] === "png" && !choice("output.format", "svg") && !choice("output.format", "gif"), params());
  return {passed: !failures.length && !errors.length, assertions, failures, errors};
}
void run().catch(error => ({passed: false, assertions, failures, errors: [...errors, String(error)]})).then(async report => { output.textContent = JSON.stringify(report); await fetch("/qa-results", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(report)}); });
