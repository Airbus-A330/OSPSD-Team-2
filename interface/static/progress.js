// Presentation only: all service requests and authorization stay in Python/services.
document.querySelectorAll("form[data-progress]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    if (form.dataset.submitted) { event.preventDefault(); return; }
    form.dataset.submitted = "true";
    if (event.submitter?.value === "reject") return;
    const waiting = document.getElementById("waiting");
    document.getElementById("waiting-message").textContent = form.dataset.progress;
    waiting.querySelector("h3").textContent = event.submitter?.value === "agent_submit" ? "Retrieving context" : "Executing";
    waiting.querySelector("ul").hidden = event.submitter?.value !== "execute";
    waiting.hidden = false;
    waiting.scrollIntoView({ block: "nearest" });
    // Preserve the clicked button's value in native form submission.
    setTimeout(() => form.querySelectorAll("button").forEach((button) => { button.disabled = true; }), 0);
  });
});
window.addEventListener("pageshow", () => {
  document.querySelectorAll("form[data-progress]").forEach((form) => {
    delete form.dataset.submitted;
    form.querySelectorAll("button").forEach((button) => { button.disabled = false; });
  });
  document.getElementById("waiting").hidden = true;
});
