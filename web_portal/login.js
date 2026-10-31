(() => {
  // Transparently pass ngrok header for proxied web deployments
  const _origFetch = window.fetch;
  window.fetch = function(url, init = {}) {
    init = {...init};
    init.headers = init.headers ? (init.headers instanceof Headers ? new Headers(init.headers) : {...init.headers}) : {};
    if (init.headers instanceof Headers) {
      init.headers.set("ngrok-skip-browser-warning", "true");
    } else {
      init.headers["ngrok-skip-browser-warning"] = "true";
    }
    return _origFetch.call(this, url, init);
  };

  const form = document.querySelector("#login-form");
  const message = document.querySelector("#message");
  const status = document.querySelector("#status");
  const button = document.querySelector("#submit");
  const choice = document.querySelector("#workspace-choice");
  const membershipSelect = document.querySelector("#membership");
  let pendingLogin = null;

  form.addEventListener("submit", async event => {
    event.preventDefault();
    message.textContent = "";
    status.textContent = "";
    const username = pendingLogin?.username || document.querySelector("#username").value;
    const password = pendingLogin?.password || document.querySelector("#password").value;
    const membershipId = pendingLogin ? membershipSelect.value : "";
    if (!password) {
      message.textContent = "Enter your password and try again.";
      return;
    }
    button.disabled = true;
    button.textContent = "Signing in…";
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({username, password, ...(membershipId ? {membership_id: membershipId} : {})}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Unable to sign in.");
      if (data.needs_membership_selection) {
        pendingLogin = {username, password};
        document.querySelector("#password").value = "";
        membershipSelect.innerHTML = data.memberships.map(item => {
          const option = document.createElement("option");
          option.value = item.id;
          option.textContent = `${item.merchant_name} · ${item.store_name} (${item.role.toLowerCase()})`;
          return option.outerHTML;
        }).join("");
        choice.hidden = false;
        button.textContent = "Continue";
        status.textContent = "Choose the merchant workspace for this session.";
        return;
      }
      pendingLogin = null;
      document.querySelector("#password").value = "";
      window.location.replace("/");
    } catch (error) {
      pendingLogin = null;
      document.querySelector("#password").value = "";
      message.textContent = error.message || "Unable to sign in.";
      button.textContent = "Sign in";
    } finally {
      button.disabled = false;
    }
  });

  const tabLogin = document.querySelector("#tab-login");
  const tabRegister = document.querySelector("#tab-register");
  const loginSection = document.querySelector("#login-section");
  const registerSection = document.querySelector("#register-section");
  const regForm = document.querySelector("#register-form");
  const regMessage = document.querySelector("#reg-message");
  const regStatus = document.querySelector("#reg-status");
  const regSubmit = document.querySelector("#reg-submit");

  tabLogin?.addEventListener("click", () => {
    tabLogin.classList.add("active");
    tabRegister.classList.remove("active");
    loginSection.hidden = false;
    registerSection.hidden = true;
    message.textContent = "";
    status.textContent = "";
  });

  tabRegister?.addEventListener("click", () => {
    tabRegister.classList.add("active");
    tabLogin.classList.remove("active");
    registerSection.hidden = false;
    loginSection.hidden = true;
    regMessage.textContent = "";
    regStatus.textContent = "";
  });

  regForm?.addEventListener("submit", async event => {
    event.preventDefault();
    regMessage.textContent = "";
    regStatus.textContent = "";
    const business_name = document.querySelector("#reg-business").value.trim();
    const store_name = document.querySelector("#reg-store").value.trim();
    const username = document.querySelector("#reg-username").value.trim();
    const password = document.querySelector("#reg-password").value;
    const city = document.querySelector("#reg-city").value.trim() || undefined;
    const phone = document.querySelector("#reg-phone").value.trim() || undefined;

    if (!business_name || !store_name || !username || !password) {
      regMessage.textContent = "Please fill in all required fields.";
      return;
    }
    if (password.length < 14) {
      regMessage.textContent = "Password must be at least 14 characters.";
      return;
    }

    regSubmit.disabled = true;
    regSubmit.textContent = "Creating store…";
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        credentials: "same-origin",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({business_name, store_name, username, password, city, phone}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Unable to register store.");
      regStatus.textContent = "Store created! Redirecting to console…";
      window.location.replace("/");
    } catch (error) {
      regMessage.textContent = error.message || "Registration failed.";
      regSubmit.textContent = "Register & Open Store";
      regSubmit.disabled = false;
    }
  });

  fetch("/api/auth/session", {credentials:"same-origin", cache:"no-store"})
    .then(response => response.ok ? response.json() : null)
    .then(data => { if (data?.authenticated) window.location.replace("/"); })
    .catch(() => {});
})();
