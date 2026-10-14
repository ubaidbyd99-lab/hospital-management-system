function confirmAction(message) {
  return window.confirm(message || "Are you sure?");
}

function toggleSidebar() {
  const sidebar = document.querySelector(".sidebar");
  if (sidebar) {
    sidebar.classList.toggle("open");
  }
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (form.dataset.confirm) {
    if (!confirmAction(form.dataset.confirm)) {
      event.preventDefault();
    }
  }
});
