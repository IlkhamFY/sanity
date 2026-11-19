import "@fontsource/schibsted-grotesk/400.css";
import "@fontsource/schibsted-grotesk/500.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "katex/dist/katex.min.css";
import katex from "katex";
import "./style.css";
import "./papers.css";

const liveEl = document.querySelector("#live");
const filtersEl = document.querySelector("#filters");
const gridEl = document.querySelector("#grid");
const detailEl = document.querySelector("#detail");

let papers = [];
let events = [];
let lastPapers = "";
let lastEvents = "";
let subject = "All";
let status = "All";
let query = "";
let examples = false;
let builtFilters = false;
const runs = new Map();

function stamp(value) {
  if (!value) return NaN;
  const zoned = /(?:Z|[+-]\d\d:?\d\d)$/.test(value) ? value : `${value}Z`;
  return Date.parse(zoned);
}

function ago(value, now) {
  const then = stamp(value);
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((now - then) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 36) return `${hours} hr ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

function newestEvent(list) {
  let best = null;
  for (const event of list) {
    if (!event.time || Number.isNaN(stamp(event.time))) continue;
    if (!best || stamp(event.time) > stamp(best.time)) best = event;
  }
  return best;
}

function isFlagged(paper) {
  return (paper.counts && paper.counts.fails > 0) || (paper.segments || []).includes("FAILS");
}

function tagOf(paper) {
  if (paper.status === "checking") return { text: "Checking", kind: "" };
  if (isFlagged(paper)) return { text: "Flagged", kind: "flag" };
  return { text: "Clean", kind: "clean" };
}

function logo(file, label, kind) {
  if (file.endsWith(".svg") && kind !== "word") {
    const node = document.createElement("span");
    node.className = `mark-svg ${kind || "tool"}`;
    const mask = `url("./logos/${file}") center / contain no-repeat`;
    node.style.setProperty("-webkit-mask", mask);
    node.style.setProperty("mask", mask);
    node.setAttribute("role", "img");
    node.setAttribute("aria-label", label);
    node.title = label;
    return node;
  }
  const image = document.createElement("img");
  image.className = "mark-img";
  image.src = `./logos/${file}`;
  image.alt = label;
  image.decoding = "async";
  image.addEventListener("error", () => image.remove());
  return image;
}

function marks(paper) {
  const row = document.createElement("span");
  row.className = "marks";
  for (const mark of paper.marks || []) {
    if (!mark.logo) continue;
    const link = document.createElement("a");
    link.href = mark.href || paper.source_url || "#";
    if (mark.href || paper.source_url) {
      link.target = "_blank";
      link.rel = "noreferrer";
    }
    const kind = mark.name === "arXiv" || mark.name === "Springer" ? "word" : "tool";
    link.append(logo(mark.logo, mark.name, kind));
    link.addEventListener("click", (event) => event.stopPropagation());
    row.append(link);
  }
  return row;
}

function bar(paper) {
  const row = document.createElement("span");
  row.className = "bar";
  row.setAttribute("aria-hidden", "true");
  for (const verdict of paper.segments || []) {
    const seg = document.createElement("i");
    seg.className = "seg";
    seg.dataset.v = verdict;
    row.append(seg);
  }
  return row;
}

function openPaper(slug) {
  const url = new URL(location.href);
  url.searchParams.set("paper", slug);
  history.pushState({ paper: slug }, "", url);
  show();
}

function closePaper() {
  const url = new URL(location.href);
  url.searchParams.delete("paper");
  history.pushState({}, "", url);
  show();
}

function selectedSlug() {
  return new URL(location.href).searchParams.get("paper");
}

function matches(paper) {
  if (!examples && paper.example) return false;
  if (subject !== "All" && paper.subject !== subject) return false;
  const flagged = isFlagged(paper);
  if (status === "Flagged" && !flagged) return false;
  if (status === "Clean" && (flagged || paper.status === "checking")) return false;
  const hay = [paper.title, paper.subject, ...(paper.authors || [])].join(" ").toLowerCase();
  return hay.includes(query.trim().toLowerCase());
}

function ordered(list) {
  return list.slice().sort((a, b) => {
    const flag = Number(isFlagged(b)) - Number(isFlagged(a));
    if (flag) return flag;
    const example = Number(Boolean(a.example)) - Number(Boolean(b.example));
    if (example) return example;
    return stamp(b.checked_at) - stamp(a.checked_at);
  });
}

function liveLine(now) {
  const flagged = papers.filter(isFlagged).length;
  const newest = newestEvent(events);
  const when = newest ? ago(newest.time, now) : "";
  const bits = [`${papers.length} paper${papers.length === 1 ? "" : "s"}`, `${flagged} flagged`];
  if (when) bits.push(`updated ${when}`);
  liveEl.textContent = bits.join(" · ");
}

function chip(label, pressed, on) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "fchip";
  button.textContent = label;
  button.setAttribute("aria-pressed", pressed ? "true" : "false");
  button.addEventListener("click", on);
  return button;
}

function renderFilters() {
  const focus = document.activeElement === filtersEl.querySelector("input");
  const caret = focus ? filtersEl.querySelector("input").selectionStart : null;
  filtersEl.replaceChildren();
  const listed = examples ? papers : papers.filter((paper) => !paper.example);
  const subjects = ["All", ...new Set(listed.map((paper) => paper.subject).filter(Boolean))];
  if (!subjects.includes(subject)) subject = "All";
  for (const name of subjects) {
    filtersEl.append(chip(name, subject === name, () => { subject = name; renderGrid(); renderFilters(); }));
  }
  if (papers.some((paper) => paper.example)) {
    filtersEl.append(chip("Examples", examples, () => { examples = !examples; renderGrid(); renderFilters(); }));
  }
  const toggle = document.createElement("div");
  toggle.className = "status";
  toggle.setAttribute("role", "group");
  toggle.setAttribute("aria-label", "Status");
  for (const name of ["All", "Flagged", "Clean"]) {
    toggle.append(chip(name, status === name, () => { status = name; renderGrid(); renderFilters(); }));
  }
  filtersEl.append(toggle);
  const search = document.createElement("label");
  search.className = "search";
  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = "Search";
  input.setAttribute("aria-label", "Search papers");
  input.value = query;
  input.addEventListener("input", () => {
    query = input.value;
    renderGrid();
  });
  search.append(input);
  filtersEl.append(search);
  if (focus) {
    input.focus();
    if (caret != null) input.setSelectionRange(caret, caret);
  }
  builtFilters = true;
}

function pageFrame(paper, { detail }) {
  const frame = document.createElement(detail ? "figure" : "span");
  frame.className = "page";
  if (paper.preview) {
    const image = document.createElement("img");
    image.src = `./data/${paper.preview}`;
    image.alt = detail ? `First page of ${paper.title}` : "";
    image.decoding = "async";
    if (!detail) image.loading = "lazy";
    image.addEventListener("error", () => frame.remove());
    frame.append(image);
    return frame;
  }
  if (!paper.first_page) return null;
  const iframe = document.createElement("iframe");
  iframe.src = paper.first_page;
  iframe.title = `First page of ${paper.title}`;
  iframe.loading = "lazy";
  frame.append(iframe);
  return frame;
}

function card(paper) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "card";
  button.addEventListener("click", () => openPaper(paper.slug));
  const frame = pageFrame(paper, { detail: false });
  if (frame) button.append(frame);
  const head = document.createElement("span");
  head.className = "meta";
  head.append(marks(paper));
  button.append(head);
  const title = document.createElement("h2");
  title.textContent = paper.title;
  button.append(title);
  const subjectLine = document.createElement("p");
  subjectLine.className = "subject-name";
  subjectLine.textContent = paper.subject || "";
  button.append(subjectLine);
  button.append(bar(paper));
  const tags = document.createElement("span");
  tags.className = "tags";
  const tag = tagOf(paper);
  const statusTag = document.createElement("span");
  statusTag.className = `tag ${tag.kind}`;
  statusTag.textContent = tag.text;
  tags.append(statusTag);
  if (paper.example) {
    const example = document.createElement("span");
    example.className = "tag";
    example.textContent = "Example";
    tags.append(example);
  }
  button.append(tags);
  return button;
}

function renderGrid() {
  const shown = ordered(papers.filter(matches));
  gridEl.replaceChildren();
  if (!shown.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Nothing matches.";
    gridEl.append(empty);
    return;
  }
  for (const paper of shown) gridEl.append(card(paper));
}

function math(latex, host) {
  const node = document.createElement("span");
  node.className = "math";
  try {
    katex.render(latex, node, { throwOnError: false, displayMode: true });
  } catch {
    node.textContent = latex;
  }
  host.append(node);
}

function printedLabel(paper) {
  return /v1(?:\b|\/|$)/i.test(paper.source_url || "") ? "Printed (v1)" : "Printed";
}

function catchBlock(paper) {
  const flags = (paper.flags || []).filter((flag) => flag.crop || flag.correction_latex);
  if (!flags.length) return null;
  const section = document.createElement("section");
  section.className = "section";
  const heading = document.createElement("h3");
  heading.textContent = "The catch";
  section.append(heading);
  for (const flag of flags) {
    const pair = document.createElement("div");
    pair.className = "pair";
    if (flag.crop) {
      const printed = document.createElement("figure");
      printed.className = "crop";
      const label = document.createElement("p");
      label.className = "side";
      label.textContent = printedLabel(paper);
      const image = document.createElement("img");
      image.src = `./data/${flag.crop}`;
      image.alt = flag.claim ? `Printed equation ${flag.claim}` : "Printed equation";
      image.addEventListener("error", () => printed.remove());
      printed.append(label, image);
      pair.append(printed);
    }
    if (flag.correction_latex) {
      const corrected = document.createElement("div");
      corrected.className = "fix";
      const label = document.createElement("p");
      label.className = "side";
      label.textContent = "Corrected";
      corrected.append(label);
      math(flag.correction_latex, corrected);
      pair.append(corrected);
    }
    section.append(pair);
  }
  return section;
}

function claimRows(run) {
  const claims = (run && run.verdicts && run.verdicts.claims) || [];
  if (!claims.length) return null;
  const numbers = new Map(
    ((run.equations && run.equations.equations) || []).map((equation) => [equation.id, equation.number || equation.id])
  );
  const section = document.createElement("section");
  section.className = "section";
  const heading = document.createElement("h3");
  heading.textContent = "Claims";
  const list = document.createElement("ol");
  list.className = "claims";
  for (const claim of claims) {
    const row = document.createElement("li");
    row.className = "claim";
    const name = document.createElement("span");
    const number = numbers.get(claim.claim) || claim.claim;
    name.textContent = `(${number})`;
    const verdict = document.createElement("span");
    verdict.className = "v";
    verdict.dataset.v = claim.verdict || "UNCHECKED";
    verdict.textContent = claim.verdict || "UNCHECKED";
    row.append(name, verdict);
    list.append(row);
  }
  section.append(heading, list);
  return section;
}

function toolRow(paper) {
  if (!(paper.tools || []).length) return null;
  const section = document.createElement("section");
  section.className = "section";
  const heading = document.createElement("h3");
  heading.textContent = "Tools";
  const row = document.createElement("div");
  row.className = "tools";
  for (const tool of paper.tools) {
    const item = document.createElement("span");
    item.className = "tool";
    if (tool.logo) item.append(logo(tool.logo, tool.name, "tool"));
    const name = document.createElement("span");
    name.textContent = tool.name;
    item.append(name);
    row.append(item);
  }
  section.append(heading, row);
  return section;
}

function activity(paper) {
  const mine = events.filter((event) => event.slug === paper.slug && event.time);
  const lines = (paper.telegram && paper.telegram.lines) || [];
  if (!mine.length && !lines.length) return null;
  const section = document.createElement("section");
  section.className = "section";
  const heading = document.createElement("h3");
  heading.textContent = "Activity";
  const list = document.createElement("ol");
  list.className = "activity";
  for (const event of mine) {
    const item = document.createElement("li");
    const text = document.createElement("p");
    const role = document.createElement("span");
    role.className = "role";
    role.append(logo("telegram.svg", "Telegram", "tg"));
    const who = document.createElement("span");
    who.textContent = event.role ? event.role[0].toUpperCase() + event.role.slice(1) : "Bot";
    role.append(who);
    text.append(role);
    text.append(document.createTextNode(` ${event.event || ""}`.trimEnd()));
    if (event.detail) text.append(document.createTextNode(` — ${event.detail}`));
    const when = document.createElement("p");
    when.className = "when";
    when.textContent = ago(event.time, Date.now());
    item.append(text, when);
    list.append(item);
  }
  for (const line of lines) {
    const item = document.createElement("li");
    const text = document.createElement("p");
    const prefix = `${paper.slug}: `;
    text.textContent = line.startsWith(prefix) ? line.slice(prefix.length) : line;
    item.append(text);
    list.append(item);
  }
  section.append(heading, list);
  return section;
}

async function loadRun(slug) {
  if (runs.has(slug)) return runs.get(slug);
  const pull = async (name) => {
    const response = await fetch(`./data/${slug}/${name}.json`);
    return response.ok ? response.json() : null;
  };
  const [equations, verdicts] = await Promise.all([pull("equations"), pull("verdicts")]);
  const run = { equations, verdicts };
  runs.set(slug, run);
  return run;
}

async function renderDetail(paper) {
  detailEl.hidden = false;
  filtersEl.hidden = true;
  gridEl.hidden = true;
  detailEl.replaceChildren();
  const back = document.createElement("p");
  back.className = "back";
  const link = document.createElement("a");
  link.href = "./papers.html";
  link.textContent = "Checked papers";
  link.addEventListener("click", (event) => {
    event.preventDefault();
    closePaper();
  });
  back.append(link);
  const head = document.createElement("div");
  head.className = "detail-head";
  const frame = pageFrame(paper, { detail: true });
  if (frame) head.append(frame);
  const copy = document.createElement("div");
  copy.append(marks(paper));
  const title = document.createElement("h2");
  title.textContent = paper.title;
  copy.append(title);
  if (paper.subject) {
    const subjectLine = document.createElement("p");
    subjectLine.className = "subject-name";
    subjectLine.textContent = paper.subject;
    copy.append(subjectLine);
  }
  const tags = document.createElement("p");
  tags.className = "tags";
  const tag = tagOf(paper);
  const statusTag = document.createElement("span");
  statusTag.className = `tag ${tag.kind}`;
  statusTag.textContent = tag.text;
  tags.append(statusTag);
  if (paper.example) {
    const example = document.createElement("span");
    example.className = "tag";
    example.textContent = "Example";
    tags.append(example);
  }
  copy.append(tags, bar(paper));
  head.append(copy);
  detailEl.append(back, head);
  const found = catchBlock(paper);
  if (found) detailEl.append(found);
  const run = await loadRun(paper.slug);
  if (selectedSlug() !== paper.slug) return;
  const claims = claimRows(run);
  if (claims) detailEl.append(claims);
  const tools = toolRow(paper);
  if (tools) detailEl.append(tools);
  const feed = activity(paper);
  if (feed) detailEl.append(feed);
  const more = document.createElement("p");
  more.className = "more";
  const equations = document.createElement("a");
  equations.href = `./demo.html?run=${encodeURIComponent(paper.slug)}`;
  equations.textContent = "Equations";
  more.append(equations);
  detailEl.append(more);
  document.title = `${paper.title} — Sanity`;
}

function show() {
  liveLine(Date.now());
  const slug = selectedSlug();
  const paper = slug && papers.find((item) => item.slug === slug);
  if (paper) {
    renderDetail(paper);
    return;
  }
  detailEl.hidden = true;
  detailEl.replaceChildren();
  filtersEl.hidden = false;
  gridEl.hidden = false;
  document.title = "Checked papers — Sanity";
  if (!builtFilters) renderFilters();
  renderGrid();
}

async function poll() {
  const bust = Date.now();
  const [paperRes, eventRes] = await Promise.all([
    fetch(`./data/papers.json?t=${bust}`),
    fetch(`./data/activity.json?t=${bust}`),
  ]);
  if (!paperRes.ok) return;
  const paperText = await paperRes.text();
  const eventText = eventRes.ok ? await eventRes.text() : lastEvents;
  const changed = paperText !== lastPapers || eventText !== lastEvents;
  lastPapers = paperText;
  lastEvents = eventText;
  if (!changed && builtFilters) {
    liveLine(Date.now());
    return;
  }
  papers = JSON.parse(paperText).papers || [];
  events = eventText ? (JSON.parse(eventText).events || []) : [];
  runs.clear();
  builtFilters = false;
  show();
}

window.addEventListener("popstate", show);
poll();
setInterval(poll, 15000);
