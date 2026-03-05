/**
 * Consent UI — Shadow DOM popup for requesting user consent.
 *
 * Uses Shadow DOM to isolate styles from the host page.
 * Returns a Promise<boolean> that resolves when the user clicks Allow/Deny.
 */

export function showConsentUI(message: string): Promise<boolean> {
  return new Promise((resolve) => {
    // Create host element
    const host = document.createElement("div");
    host.id = "openclaw-consent-host";
    const shadow = host.attachShadow({ mode: "closed" });

    shadow.innerHTML = `
      <style>
        .overlay {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0, 0, 0, 0.5);
          z-index: 2147483647;
          display: flex;
          align-items: center;
          justify-content: center;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }
        .dialog {
          background: #fff;
          border-radius: 12px;
          padding: 24px;
          max-width: 420px;
          width: 90%;
          box-shadow: 0 8px 32px rgba(0,0,0,0.3);
        }
        .title {
          font-size: 16px;
          font-weight: 600;
          color: #1a1a1a;
          margin: 0 0 8px;
        }
        .message {
          font-size: 14px;
          color: #555;
          margin: 0 0 20px;
          line-height: 1.5;
        }
        .actions {
          display: flex;
          gap: 12px;
          justify-content: flex-end;
        }
        button {
          padding: 8px 20px;
          border-radius: 8px;
          font-size: 14px;
          font-weight: 500;
          cursor: pointer;
          border: none;
          transition: background 0.15s;
        }
        .deny {
          background: #e5e5e5;
          color: #333;
        }
        .deny:hover { background: #d5d5d5; }
        .allow {
          background: #2563eb;
          color: #fff;
        }
        .allow:hover { background: #1d4ed8; }
      </style>
      <div class="overlay">
        <div class="dialog">
          <p class="title">Openclaw — Memory Access</p>
          <p class="message">${escapeHtml(message)}</p>
          <div class="actions">
            <button class="deny">Deny</button>
            <button class="allow">Allow</button>
          </div>
        </div>
      </div>
    `;

    const cleanup = (result: boolean) => {
      host.remove();
      resolve(result);
    };

    shadow.querySelector(".allow")!.addEventListener("click", () => cleanup(true));
    shadow.querySelector(".deny")!.addEventListener("click", () => cleanup(false));
    shadow.querySelector(".overlay")!.addEventListener("click", (e) => {
      if ((e.target as Element).classList.contains("overlay")) cleanup(false);
    });

    document.body.appendChild(host);
  });
}

function escapeHtml(s: string): string {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}
