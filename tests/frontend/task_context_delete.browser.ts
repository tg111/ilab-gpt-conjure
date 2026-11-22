import { loadAcceptanceFrame, prepareFixtureOrigin } from "./browser_acceptance";

const frame = document.querySelector<HTMLIFrameElement>("#historyFrame")!;
const output = document.querySelector<HTMLElement>("#results")!;
const errors: string[] = [];
const failures: string[] = [];
let assertions = 0;

async function until(predicate: () => boolean, label: string): Promise<void> {
  const deadline = Date.now() + 6000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error(`Timed out: ${label}`);
    await new Promise(resolve => setTimeout(resolve, 25));
  }
}

function check(name: string, condition: boolean): void {
  assertions++;
  if (!condition) failures.push(name);
}

async function run(): Promise<void> {
  await prepareFixtureOrigin();
  await loadAcceptanceFrame(frame, "/qa-app", errors);
  const win = frame.contentWindow!;
  const doc = frame.contentDocument!;
  const find = <T extends HTMLElement = HTMLElement>(selector: string) => doc.querySelector<T>(selector)!;
  const taskId = "qa-history-0674";
  const prompt = "Synthetic QA history 0674";
  const cardSelector = `.task-card[data-task-id="${taskId}"]`;
  const deleteRequests: Array<{ path: string; reply: (response: Response) => void }> = [];
  const fetch = win.fetch.bind(win);
  win.fetch = (input, init) => {
    const url = new URL(input instanceof win.Request ? input.url : String(input), win.location.href);
    if (init?.method === "DELETE" && url.pathname.startsWith("/api/tasks/")) {
      return new Promise<Response>(reply => deleteRequests.push({ path: url.pathname, reply }));
    }
    return fetch(input, init);
  };

  const search = find<HTMLInputElement>("#taskSearch");
  search.dispatchEvent(new win.Event("paste", { bubbles: true }));
  search.value = prompt;
  search.dispatchEvent(new win.Event("input", { bubbles: true }));
  await until(() => Boolean(find(cardSelector)), "synthetic task card mounted");
  const card = find(cardSelector);
  if (!card?.getClientRects().length) throw new Error("Synthetic task card did not render");
  card.focus();

  const menuDelete = () => find<HTMLButtonElement>('[data-task-context-action="delete"]');
  const confirm = () => doc.querySelector<HTMLElement>(".confirm-popover:not(.hidden)");
  const settle = () => new Promise<void>(resolve => setTimeout(resolve, 0));
  const openMenu = (card: HTMLElement) => {
    const { left, top } = card.getBoundingClientRect();
    card.dispatchEvent(new win.MouseEvent("contextmenu", { bubbles: true, clientX: left + 16, clientY: top + 16 }));
  };

  // The context menu deletes immediately: no confirmation step.
  openMenu(card);
  menuDelete().click();
  await settle();
  check("one menu click deletes without a confirmation and closes the menu", !confirm()
    && !doc.querySelector(".task-context-menu:not(.hidden)")
    && !card.classList.contains("task-card-swipe-open"));
  check("the click sends one delete request for the clicked task", deleteRequests.length === 1
    && deleteRequests[0]?.path === `/api/tasks/${taskId}`);

  const { state, methods } = win.__codexImageWebUI!;
  state.tasksRenderKey = null;
  methods.renderTasks();
  await until(() => Boolean(find(cardSelector)), "card remounted during delete");
  openMenu(find(cardSelector));
  check("delete is disabled on a remounted card while its request is in flight", menuDelete().disabled);
  menuDelete().click();
  await settle();
  check("reopening the menu cannot send a second delete", !confirm() && deleteRequests.length === 1);
  doc.dispatchEvent(new win.KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await settle();

  const failure = "QA task retained";
  deleteRequests.splice(0).forEach(request => request.reply(new win.Response(JSON.stringify({ detail: failure }), { status: 409 })));
  await until(() => find("#statusText").textContent === failure, "failed delete settled");
  openMenu(find(cardSelector));
  check("failure unlocks deletion for another attempt", !menuDelete().disabled);
  menuDelete().click();
  await settle();
  check("an unlocked task can be deleted again", !confirm() && deleteRequests.length === 1);
  deleteRequests.splice(0).forEach(request => request.reply(new win.Response(JSON.stringify({ detail: failure }), { status: 409 })));
  await until(() => !find(cardSelector)?.classList.contains("task-card-removing"), "second delete settled");
}

void run().catch(error => { failures.push(String(error)); }).then(() => {
  output.textContent = JSON.stringify({ passed: !failures.length && !errors.length, assertions, failures, errors });
});
