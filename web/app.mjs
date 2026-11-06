const servicesElement = document.querySelector("#services");
const connectionElement = document.querySelector("#connection");
const connectionLabel = document.querySelector("#connection-label");
const messageElement = document.querySelector("#message");
const shutdownButton = document.querySelector("#shutdown-button");

function setConnection(state, label) {
  connectionElement.classList.toggle("is-connected", state === "connected");
  connectionElement.classList.toggle("is-error", state === "error");
  connectionLabel.textContent = label;
}

function setMessage(message, isError = false) {
  messageElement.textContent = message;
  messageElement.classList.toggle("is-error", isError);
}

function setActiveService(activeButton) {
  for (const button of servicesElement.querySelectorAll(".service-button")) {
    const isActive = button === activeButton;
    button.setAttribute("aria-pressed", String(isActive));
    button.querySelector(".service-status").hidden = !isActive;
  }
}

async function sendRequest(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok) {
    throw new Error(result.error || "Anfrage fehlgeschlagen");
  }
  return result;
}

function createServiceButton(service) {
  const button = document.createElement("button");
  button.className = "service-button";
  button.type = "button";
  button.setAttribute("aria-label", `${service.name} auf dem Bildschirm öffnen`);
  button.setAttribute("aria-pressed", "false");

  const mark = document.createElement("span");
  mark.className = `service-mark service-mark--${service.id}`;
  mark.setAttribute("aria-hidden", "true");
  mark.textContent = service.name.trim().charAt(0).toUpperCase();

  const name = document.createElement("span");
  name.className = "service-name";
  name.textContent = service.name;

  const status = document.createElement("span");
  status.className = "service-status";
  status.textContent = "Zuletzt an Firefox übergeben";
  status.hidden = true;

  const details = document.createElement("span");
  details.className = "service-details";
  details.append(name, status);

  const arrow = document.createElement("span");
  arrow.className = "service-open";
  arrow.setAttribute("aria-hidden", "true");
  arrow.textContent = "→";

  button.append(mark, details, arrow);
  button.addEventListener("click", async () => {
    button.disabled = true;
    setMessage(`${service.name} wird geöffnet …`);
    try {
      await sendRequest(`/api/services/${encodeURIComponent(service.id)}/open`, {});
      setActiveService(button);
      setMessage(`${service.name} wurde an Firefox übergeben.`);
    } catch (error) {
      setMessage(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  return button;
}

async function loadServices() {
  try {
    const response = await fetch("/api/services", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Diensteliste konnte nicht geladen werden.");
    }
    const services = await response.json();
    servicesElement.replaceChildren();
    if (services.length === 0) {
      const emptyState = document.createElement("p");
      emptyState.className = "empty-state";
      emptyState.textContent = "Keine Streaming-Dienste konfiguriert.";
      servicesElement.append(emptyState);
    } else {
      services.forEach((service) => servicesElement.append(createServiceButton(service)));
    }
    setConnection("connected", "Verbunden");
  } catch (error) {
    const loadingState = document.querySelector("#loading-state");
    if (loadingState) {
      loadingState.textContent = "Verbindung zum Server fehlgeschlagen.";
    }
    setConnection("error", "Nicht verbunden");
    setMessage(error.message, true);
  }
}

shutdownButton.addEventListener("click", async () => {
  const confirmed = window.confirm("Soll der Linux-Server jetzt ausgeschaltet werden?");
  if (!confirmed) {
    return;
  }
  shutdownButton.disabled = true;
  setMessage("Shutdown wird angefordert …");
  try {
    await sendRequest("/api/shutdown", { confirm: true });
    setMessage("Der Server fährt herunter.");
  } catch (error) {
    setMessage(error.message, true);
    shutdownButton.disabled = false;
  }
});

await loadServices();