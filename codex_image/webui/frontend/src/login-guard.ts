// Sends the page back to the sign-in screen once the server reports that the
// session is gone (signed out elsewhere, or the login file was reset).
const LOGIN_REQUIRED_HEADER = "X-Conjure-Login";

let redirecting = false;

function returnToSignIn(): void {
  if (redirecting) return;
  redirecting = true;
  window.location.reload();
}

export function installLoginGuard(): void {
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args: Parameters<typeof fetch>): Promise<Response> => {
    const response = await originalFetch(...args);
    if (response.status === 401 && response.headers.get(LOGIN_REQUIRED_HEADER) === "required") {
      returnToSignIn();
    }
    return response;
  };
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    originalFetch("/api/login/status", { cache: "no-store", credentials: "same-origin" })
      .then((response) => (response.ok ? response.json() : null))
      .then((status: { configured?: boolean; authenticated?: boolean } | null) => {
        if (status && status.configured && !status.authenticated) returnToSignIn();
      })
      .catch(() => undefined);
  });
}

installLoginGuard();
