import "@fontsource/schibsted-grotesk/400.css";
import "@fontsource/schibsted-grotesk/500.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "katex/dist/katex.min.css";
import katex from "katex";
import "./style.css";
import "./paper.css";

const RUNS = {
  paper: {
    id: "arxiv-2410-11128",
    href: "https://arxiv.org/abs/2410.11128v1",
    hrefLabel: "arXiv:2410.11128v1",
    blurb:
      "Sanity flags Eq. (4.4) in v1 and proposes the same fix the authors recorded on arXiv.",
    note: "",
  },
  toy: {
    id: "example-oscillator",
    href: null,
    hrefLabel: "",
    blurb: "Example data. Not a published paper.",
    note: "",
  },
};

const titleEl = document.querySelector("#paper-title");
const linkEl = document.querySelector("#paper-link");
const blurbEl = document.querySelector("#paper-blurb");
const countEl = document.querySelector("#paper-count");
const noteEl = document.querySelector("#paper-note");
const listEl = document.querySelector("#claims");
const tabs = {
  paper: document.querySelector("#tab-paper"),
  toy: document.querySelector("#tab-toy"),
};

function tex(value, display) {
  const node = document.createElement("span");
  node.className = "math";
  katex.render(value, node, { throwOnError: false, displayMode: display });
  return node;
}

function countLine(claims) {
  const tally = { HOLDS: 0, FAILS: 0, UNCHECKED: 0 };
  for (const claim of claims) {
    if (tally[claim.verdict] !== undefined) tally[claim.verdict] += 1;
  }
  const n = claims.length;
  return `${n} equation${n === 1 ? "" : "s"} · ${tally.HOLDS} hold · ${tally.FAILS} fail · ${tally.UNCHECKED} unchecked`;
}

function panel(claim) {
  const box = document.createElement("div");
  box.className = "more";
  box.hidden = true;
  const kind = document.createElement("p");
  kind.className = "kind";
  kind.textContent = `Evidence: ${claim.evidence.kind}`;
  box.append(kind);
  if (claim.evidence.detail) {
    const detail = document.createElement("p");
    detail.textContent = claim.evidence.detail;
    box.append(detail);
  }
  if (claim.correction) {
    const label = document.createElement("p");
    label.className = "kind";
    const state = claim.correction.verified ? "verified" : "not verified";
    label.textContent = `Correction (${state}, ${claim.correction.evidence})`;
    box.append(label, tex(claim.correction.latex, true));
    if (claim.correction.detail) {
      const extra = document.createElement("p");
      extra.textContent = claim.correction.detail;
      box.append(extra);
    }
  }
  if (claim.claim === "4.4") {
    const cite = document.createElement("p");
    cite.textContent =
      "Same replacement as the authors' comment on arXiv:2410.11128v4. That comment is not on v2.";
    box.append(cite);
  }
  return box;
}

function render(equations, verdicts) {
  const byNumber = new Map(verdicts.claims.map((claim) => [claim.claim, claim]));
  listEl.replaceChildren();
  for (const equation of equations.equations) {
    const claim = byNumber.get(equation.number);
    const verdict = claim ? claim.verdict : "UNCHECKED";
    const item = document.createElement("li");
    item.className = "item";
    item.dataset.verdict = verdict;
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-expanded", "false");
    const head = document.createElement("span");
    head.className = "eqhead";
    const num = document.createElement("span");
    num.className = "ln";
    num.textContent = `(${equation.number})`;
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = verdict;
    head.append(num, tag);
    button.append(head, tex(equation.latex, true));
    const more = claim
      ? panel(claim)
      : Object.assign(document.createElement("div"), {
          className: "more",
          hidden: true,
          textContent: "No verdict for this equation.",
        });
    button.addEventListener("click", () => {
      const open = more.hidden;
      more.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    item.append(button, more);
    listEl.append(item);
  }
}

async function load(key) {
  const run = RUNS[key];
  for (const [name, button] of Object.entries(tabs)) {
    button.setAttribute("aria-selected", name === key ? "true" : "false");
  }
  const [equations, verdicts] = await Promise.all([
    fetch(`./data/${run.id}/equations.json`).then((response) => response.json()),
    fetch(`./data/${run.id}/verdicts.json`).then((response) => response.json()),
  ]);
  titleEl.textContent = equations.title || run.id;
  linkEl.replaceChildren();
  if (run.href) {
    const anchor = document.createElement("a");
    anchor.href = run.href;
    anchor.textContent = run.hrefLabel;
    anchor.rel = "noopener noreferrer";
    linkEl.append(anchor);
  }
  blurbEl.textContent = run.blurb;
  countEl.textContent = countLine(verdicts.claims);
  noteEl.textContent = run.note;
  render(equations, verdicts);
}

tabs.paper.addEventListener("click", () => load("paper"));
tabs.toy.addEventListener("click", () => load("toy"));
load("paper");
