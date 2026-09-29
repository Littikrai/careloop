(() => {
  const script = document.currentScript;
  if (!script) return;

  const token = script.dataset.token;
  if (!token) return;

  const baseUrl = new URL(script.src).origin;
  const frame = document.createElement("iframe");
  frame.src = `${baseUrl}/embed/${encodeURIComponent(token)}/`;
  frame.title = "Customer support chat";
  frame.hidden = true;
  frame.style.cssText = "position:fixed;right:24px;bottom:88px;width:min(380px,calc(100vw - 32px));height:min(620px,calc(100vh - 112px));border:0;border-radius:16px;box-shadow:0 12px 36px rgba(0,0,0,.22);background:white;z-index:2147483647;";

  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Chat";
  button.setAttribute("aria-label", "Open customer support chat");
  button.setAttribute("aria-expanded", "false");
  button.style.cssText = "position:fixed;right:24px;bottom:24px;border:0;border-radius:999px;padding:12px 18px;background:#245c4f;color:white;font:600 16px system-ui,sans-serif;cursor:pointer;box-shadow:0 4px 16px rgba(0,0,0,.2);z-index:2147483647;";

  const close = () => {
    frame.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.focus();
  };
  const toggle = () => {
    const opening = frame.hidden;
    frame.hidden = !opening;
    button.setAttribute("aria-expanded", String(opening));
    if (opening) frame.focus();
  };

  button.addEventListener("click", toggle);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !frame.hidden) close();
  });
  window.addEventListener("message", (event) => {
    if (
      event.origin === baseUrl
      && event.source === frame.contentWindow
      && event.data?.type === "customer-service-close"
    ) close();
  });
  const mount = () => document.body.append(button, frame);
  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount, { once: true });
})();
