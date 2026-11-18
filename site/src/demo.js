const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function typeset(katex) {
  document.querySelectorAll("[data-tex]").forEach((el) => {
    katex.render(el.dataset.tex, el, {
      throwOnError: false,
      displayMode: el.dataset.display !== "inline",
      output: "html",
    });
  });
}

export function mount(katex) {
  typeset(katex);

  const buttons = [...document.querySelectorAll(".run-demo")];
  const status = document.querySelector("#status");
  const region = document.querySelector("#demo");
  let timers = [];

  const steps = [
    { at: 400, run: () => say("Reader. Reading the note.") },
    { at: 1400, run: () => say("Reader. Five equations.") },
    {
      at: 2500,
      run: () => {
        dimOthers("3");
        say("Verifier. One step does not hold.");
      },
    },
    {
      at: 3700,
      run: () => {
        say("Verifier. Proved in Lean.");
      },
    },
    {
      at: 4900,
      run: () => {
        showCard();
        reveal("badge");
        say("Writer. The spring term was missing a half.");
      },
    },
    {
      at: 6400,
      run: () => {
        document.querySelector('[data-eq="4"]').classList.add("is-focus");
        say("Verifier. One more step fails on units.");
      },
    },
    {
      at: 7600,
      run: () => {
        reveal("also");
        say("Writer. The decay time is 2m/b.");
      },
    },
  ];

  function clearTimers() {
    timers.forEach((id) => clearTimeout(id));
    timers = [];
  }

  function say(text) {
    status.textContent = text;
  }

  function dimOthers(id) {
    document.querySelectorAll("[data-eq]").forEach((el) => {
      el.classList.toggle("is-dim", el.dataset.eq !== id);
      el.classList.toggle("is-focus", el.dataset.eq === id);
    });
  }

  function showCard() {
    const card = document.querySelector('[data-fix="3"]');
    card.hidden = false;
    if (!reduceMotion) card.scrollIntoView({ block: "center", behavior: "smooth" });
  }

  function reveal(part) {
    document.querySelectorAll(`[data-part="${part}"]`).forEach((el) => {
      el.hidden = false;
    });
  }

  function reset() {
    clearTimers();
    say("");
    document.querySelectorAll("[data-eq]").forEach((el) => {
      el.classList.remove("is-dim", "is-focus");
    });
    document.querySelectorAll("[data-fix], [data-part]").forEach((el) => {
      el.hidden = true;
    });
  }

  function setButtons(label, disabled) {
    buttons.forEach((button) => {
      button.disabled = disabled;
      button.textContent = label;
    });
  }

  function finish() {
    region.removeAttribute("aria-busy");
    setButtons("Run again", false);
  }

  function start(scroll) {
    reset();
    setButtons("Running", true);
    region.setAttribute("aria-busy", "true");
    if (scroll && !reduceMotion) {
      document.querySelector(`#${scroll}`).scrollIntoView({ behavior: "smooth", block: "start" });
    } else if (scroll) {
      document.querySelector(`#${scroll}`).scrollIntoView({ block: "start" });
    }
    if (reduceMotion) {
      steps.forEach((step) => step.run());
      finish();
      return;
    }
    steps.forEach((step) => {
      timers.push(window.setTimeout(step.run, step.at));
    });
    timers.push(window.setTimeout(finish, 8400));
  }

  buttons.forEach((button) => {
    button.addEventListener("click", () => start(button.dataset.scroll));
  });
}
