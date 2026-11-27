const menuToggle = document.querySelector(".menu-toggle");
const navMenu = document.querySelector(".nav-menu");

if (menuToggle && navMenu) {
  menuToggle.addEventListener("click", () => {
    const isOpen = menuToggle.getAttribute("aria-expanded") === "true";
    menuToggle.setAttribute("aria-expanded", String(!isOpen));
    menuToggle.setAttribute("aria-label", isOpen ? "打开导航菜单" : "关闭导航菜单");
    navMenu.classList.toggle("is-open", !isOpen);
  });

  navMenu.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", () => {
      menuToggle.setAttribute("aria-expanded", "false");
      menuToggle.setAttribute("aria-label", "打开导航菜单");
      navMenu.classList.remove("is-open");
    });
  });
}

const slides = Array.from(document.querySelectorAll(".hero-slide"));
const dots = Array.from(document.querySelectorAll(".carousel-dot"));
const currentSlide = document.querySelector(".current-slide");
const previousButton = document.querySelector(".carousel-prev");
const nextButton = document.querySelector(".carousel-next");
const carousel = document.querySelector(".hero-carousel");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

if (slides.length && dots.length === slides.length && carousel) {
  let activeIndex = 0;
  let rotationTimer;

  const showSlide = (index) => {
    activeIndex = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      const isActive = slideIndex === activeIndex;
      slide.classList.toggle("is-active", isActive);
      slide.setAttribute("aria-hidden", String(!isActive));
    });
    dots.forEach((dot, dotIndex) => {
      const isActive = dotIndex === activeIndex;
      dot.classList.toggle("is-active", isActive);
      dot.setAttribute("aria-pressed", String(isActive));
    });
    if (currentSlide) {
      currentSlide.textContent = String(activeIndex + 1).padStart(2, "0");
    }
  };

  const stopRotation = () => window.clearInterval(rotationTimer);
  const startRotation = () => {
    stopRotation();
    if (!reduceMotion.matches) {
      rotationTimer = window.setInterval(() => showSlide(activeIndex + 1), 6500);
    }
  };

  dots.forEach((dot) => {
    dot.addEventListener("click", () => {
      showSlide(Number(dot.dataset.goTo));
      startRotation();
    });
  });
  previousButton?.addEventListener("click", () => {
    showSlide(activeIndex - 1);
    startRotation();
  });
  nextButton?.addEventListener("click", () => {
    showSlide(activeIndex + 1);
    startRotation();
  });
  carousel.addEventListener("mouseenter", stopRotation);
  carousel.addEventListener("mouseleave", startRotation);
  carousel.addEventListener("focusin", stopRotation);
  carousel.addEventListener("focusout", startRotation);
  reduceMotion.addEventListener("change", startRotation);
  startRotation();
}
