function waitForSidebar() {
  const sidebar = document.getElementById("sidebar");

  if (!sidebar) {
    setTimeout(waitForSidebar, 100);
    return;
  }

  document.addEventListener("mousemove", function (e) {

    const rect = sidebar.getBoundingClientRect();

    if (e.clientX <= 25) {
      sidebar.classList.add("visible");
    } else if (
      e.clientX > 100 || 
      e.clientY < (rect.top - 50) || 
      e.clientY > (rect.bottom + 50)
    ) {
      sidebar.classList.remove("visible");
    }
  });
}

window.addEventListener("load", waitForSidebar);

function setupIconClickAnimations() {
  const icons = document.querySelectorAll('.icon-btn i');

  if (icons.length === 0) {
    return setTimeout(setupIconClickAnimations, 100);
  }

  console.log('Setting up icon click animations');

  icons.forEach(icon => {
    icon.parentElement.addEventListener('click', () => {
      console.log('Clicked icon:', icon.className);
      icon.classList.remove('click-animate');
      void icon.offsetWidth;
      icon.classList.add('click-animate');
    });
  });
}

window.addEventListener("load", setupIconClickAnimations);
