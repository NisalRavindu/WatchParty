const POSTER_URL = "https://image.tmdb.org/t/p/w342";
const THUMB_URL = "https://image.tmdb.org/t/p/w92";

// My movies filters. A rewatch (seen + want) shows under both Seen and Want.
const LIBRARY_FILTERS = {
  all: { label: "All", test: () => true },
  seen: { label: "Seen", test: (entry) => entry.seen },
  want: { label: "Want", test: (entry) => entry.intent === "want" },
  curious: { label: "Curious", test: (entry) => entry.intent === "curious" },
};

const state = {
  view: "search", // "search" | "library"
  libraryFilter: "all", // a LIBRARY_FILTERS key
  session: null,
  candidates: [],
  results: [],
  page: 1,
  totalPages: 1,
  library: [], // [{ movie, seen, intent, updated_at }], most recently changed first
};

const $ = (id) => document.getElementById(id);

// ---- API ----

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body && JSON.stringify(body),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status})`);
  }
  return response.status === 204 ? null : response.json();
}

function showError(message) {
  $("error").textContent = message;
  $("error").hidden = !message;
}

async function run(action) {
  showError("");
  try {
    await action();
  } catch (error) {
    showError(error.message);
  }
}

// ---- Rendering helpers ----

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function button(label, onClick, props = {}) {
  const node = el("button", { type: "button", textContent: label, ...props });
  node.addEventListener("click", onClick);
  return node;
}

function year(movie) {
  return movie.release_date ? movie.release_date.slice(0, 4) : "Unknown year";
}

function poster(movie, className, baseUrl = POSTER_URL) {
  if (!movie.poster_path) {
    return el("div", { className: `${className} no-poster`, textContent: movie.title.charAt(0) });
  }
  return el("img", { className, src: baseUrl + movie.poster_path, alt: "", loading: "lazy" });
}

const isDecided = () => state.session?.picked_movie_id != null;

const entryOf = (movieId) => state.library.find((item) => item.movie.id === movieId);

// The pill on the poster: [label, style].
function statusPill(entry) {
  if (!entry) return null;
  if (entry.seen) return entry.intent === "want" ? ["Rewatch", "want"] : ["Seen", "seen"];
  return entry.intent === "want" ? ["Want", "want"] : ["Curious", "curious"];
}

// ---- Movie cards ----

function closeStatusMenus() {
  for (const menu of document.querySelectorAll(".status-menu")) menu.hidden = true;
  for (const toggle of document.querySelectorAll(".status-toggle")) toggle.ariaExpanded = "false";
}

function statusControl(movie) {
  const entry = entryOf(movie.id);
  const seen = entry?.seen ?? false;
  const intent = entry?.intent ?? null;
  const option = (label, checked, changes) =>
    button(label, () => run(() => updateEntry(movie.id, changes)), { role: "menuitemcheckbox", ariaChecked: String(checked) });

  const menu = el(
    "div",
    { className: "status-menu", role: "menu", hidden: true },
    option("Seen it", seen, { seen: !seen }),
    option(seen ? "Want to rewatch" : "Want to watch", intent === "want", { intent: intent === "want" ? null : "want" }),
    ...(seen ? [] : [option("Curious", intent === "curious", { intent: intent === "curious" ? null : "curious" })]),
    ...(entry ? [button("Remove", () => run(() => clearEntry(movie.id)), { role: "menuitem", className: "remove" })] : []),
  );

  const pill = statusPill(entry);
  const toggle = button(
    pill ? pill[0] : "+",
    (event) => {
      event.stopPropagation(); // keep the document click handler from closing it right away
      const opening = menu.hidden;
      closeStatusMenus();
      menu.hidden = !opening;
      toggle.ariaExpanded = String(opening);
    },
    {
      className: `status-toggle ${pill ? `is-${pill[1]}` : "is-empty"}`,
      title: pill ? pill[0] : "Seen it, want to watch, or curious?",
      ariaLabel: pill ? `${movie.title}: ${pill[0]}. Change` : `Set status for ${movie.title}`,
      ariaHasPopup: "menu",
      ariaExpanded: "false",
    },
  );
  return el("div", { className: "status" }, toggle, menu);
}

function movieCard(movie) {
  const onShortlist = state.candidates.some((candidate) => candidate.id === movie.id);
  const add = button(
    onShortlist ? "On shortlist" : "Add to tonight",
    () => {
      add.disabled = true;
      add.textContent = "Adding…";
      run(() => addCandidate(movie.id));
    },
    { disabled: onShortlist || isDecided() },
  );

  return el(
    "li",
    { className: "movie-card" },
    el("div", { className: "poster-wrap" }, poster(movie, "poster"), statusControl(movie)),
    el(
      "div",
      { className: "card-body" },
      el("h3", { textContent: movie.title }),
      el("p", { className: "muted", textContent: [year(movie), ...movie.genres.slice(0, 2)].join(" · ") }),
      ...(movie.credit ? [el("p", { className: "muted credit", textContent: movie.credit })] : []),
      add,
    ),
  );
}

function renderGrid() {
  const movies =
    state.view === "search"
      ? state.results
      : state.library.filter(LIBRARY_FILTERS[state.libraryFilter].test).map((item) => item.movie);
  $("movie-grid").replaceChildren(...movies.map(movieCard));

  $("pager").hidden = state.view !== "search" || state.totalPages <= 1;
  $("page-label").textContent = `Page ${state.page} of ${state.totalPages}`;
  $("page-prev").disabled = state.page <= 1;
  $("page-next").disabled = state.page >= state.totalPages;

  if (state.view === "library") {
    $("library-empty").hidden = movies.length > 0;
    $("library-empty").textContent = state.library.length
      ? "Nothing with this status yet."
      : "Nothing here yet. Use the + on any poster to say you've seen it, want to watch it, or are curious.";
  }
}

// ---- Views ----

function showView(view) {
  state.view = view;
  $("search-view").hidden = view !== "search";
  $("library-view").hidden = view !== "library";
  $("tab-search").ariaPressed = String(view === "search");
  $("tab-library").ariaPressed = String(view === "library");
  renderGrid();
}

function renderLibraryChrome() {
  $("library-count").textContent = state.library.length || "";

  $("library-filters").replaceChildren(
    ...Object.entries(LIBRARY_FILTERS).map(([value, { label, test }]) =>
      button(
        `${label} ${state.library.filter(test).length}`,
        () => {
          state.libraryFilter = value;
          renderLibraryChrome();
          renderGrid();
        },
        { className: "chip", ariaPressed: String(state.libraryFilter === value) },
      ),
    ),
  );
}

// ---- Library ----

async function loadLibrary() {
  state.library = await api("/library");
  renderLibraryChrome();
  renderGrid();
  if (state.session) renderSession();
}

async function updateEntry(movieId, changes) {
  await api(`/library/${movieId}`, { method: "PATCH", body: changes });
  await loadLibrary();
}

async function clearEntry(movieId) {
  await api(`/library/${movieId}`, { method: "DELETE" });
  await loadLibrary();
}

// ---- Search ----

const PLACEHOLDERS = {
  title: "Search for a movie…",
  person: "Search for a person, e.g. an actor, director or composer…",
  keyword: "Search a theme, e.g. alien + small town, or avoid one: -horror…",
  studio: "Search a studio, e.g. Disney + Pixar, or leave one out: -marvel…",
};

let searchTimer;
let latestSearch = 0;

function searchParams(query, page) {
  const by = $("search-by").value;
  const params = new URLSearchParams({ q: query, by, sort: $("sort").value, page });
  if (by === "person") params.set("role", $("role").value);
  if (by === "keyword") params.set("match", $("match").value);
  for (const [key, id] of [["genre", "genre"], ["year_from", "year-from"], ["year_to", "year-to"], ["language", "language"]]) {
    const value = $(id).value.trim();
    if (value) params.set(key, value);
  }
  if ($("include-obscure").checked) params.set("include_obscure", "true");
  if ($("include-upcoming").checked) params.set("include_upcoming", "true");
  return params;
}

// Any change to the query or filters starts again from page 1.
// The dropdown filters in words, so the status line says everything the results were narrowed by.
function filterSummary() {
  const parts = [];
  const selected = (id) => $(id).selectedOptions[0].textContent;
  if ($("genre").value) parts.push(selected("genre"));
  const from = $("year-from").value.trim();
  const to = $("year-to").value.trim();
  if (from && to) parts.push(`${from}–${to}`);
  else if (from) parts.push(`from ${from}`);
  else if (to) parts.push(`until ${to}`);
  if ($("language").value) parts.push(selected("language"));
  return parts.join(", ");
}

async function search(page = 1) {
  const query = $("search-input").value.trim();
  const searchId = ++latestSearch;

  if (!query) {
    Object.assign(state, { results: [], page: 1, totalPages: 1 });
    $("search-status").textContent = "";
    renderGrid();
    return;
  }

  $("search-status").textContent = "Searching…";
  try {
    const data = await api(`/movies/search?${searchParams(query, page)}`);
    if (searchId !== latestSearch) return; // a newer search has started
    Object.assign(state, { results: data.results, page: data.page, totalPages: data.total_pages });

    const total = data.total_results.toLocaleString();
    let count = data.total_results ? `${data.total_is_estimate ? "about " : ""}${total} movies` : "No movies found";
    const strictCombo = $("search-by").value === "keyword" && $("match").value === "all" && /[+,]/.test(query);
    if (!data.total_results && strictCombo) count += ' with all of these. Try "Any keyword".';
    const filtered = filterSummary();
    const described = [data.matched, filtered && (data.matched ? `filtered to ${filtered}` : `Filtered to ${filtered}`)];
    $("search-status").textContent = [described.filter(Boolean).join(" · "), count].filter(Boolean).join(" — ");
    renderGrid();
  } catch (error) {
    if (searchId === latestSearch) $("search-status").textContent = error.message;
  }
}

function searchSoon() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => search(), 300);
}

async function loadGenres() {
  const genres = await api("/movies/genres");
  $("genre").append(...genres.map((genre) => el("option", { value: genre.id, textContent: genre.name })));
}

// ---- Session ----

async function loadSession(sessionId) {
  const detail = await api(`/sessions/${sessionId}`);
  state.session = detail.session;
  state.candidates = detail.candidates;
  renderSession();
  renderGrid();
}

async function loadLatestSession() {
  const sessions = await api("/sessions");
  const session = sessions[0] ?? (await api("/sessions", { method: "POST" }));
  await loadSession(session.id);
}

async function startNewSession() {
  const session = await api("/sessions", { method: "POST" });
  await loadSession(session.id);
}

async function addCandidate(movieId) {
  await api(`/sessions/${state.session.id}/candidates`, { method: "POST", body: { movie_id: movieId } });
  await loadSession(state.session.id);
}

async function removeCandidate(movieId) {
  await api(`/sessions/${state.session.id}/candidates/${movieId}`, { method: "DELETE" });
  await loadSession(state.session.id);
}

async function pickMovie(movieId) {
  await api(`/sessions/${state.session.id}/pick`, { method: "POST", body: { movie_id: movieId } });
  await loadSession(state.session.id);
}

function watchedPrompt(movie) {
  const entry = entryOf(movie.id);
  if (entry?.seen && entry.intent !== "want") {
    return el("p", { className: "muted", textContent: "✓ Seen" });
  }
  // Watching it fulfils a Want, including a rewatch.
  return el(
    "div",
    { className: "watched-prompt" },
    el("span", { className: "muted", textContent: "Did you watch it?" }),
    button("Yes, seen it", () => run(() => updateEntry(movie.id, { seen: true, intent: null })), { className: "secondary" }),
  );
}

function renderSession() {
  // Timestamps are UTC; add the marker if the API left it off.
  const stamp = state.session.started_at;
  const started = new Date(/(Z|[+-]\d\d:\d\d)$/.test(stamp) ? stamp : `${stamp}Z`);
  $("session-started").textContent = `Started ${started.toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`;

  const picked = state.candidates.find((movie) => movie.id === state.session.picked_movie_id);
  $("picked").hidden = !isDecided();
  $("shortlist-section").hidden = isDecided();

  if (isDecided()) {
    $("picked").replaceChildren(
      el("p", { className: "label", textContent: "Tonight's pick" }),
      ...(picked
        ? [poster(picked, "poster"), el("h3", { textContent: `${picked.title} (${year(picked)})` }), watchedPrompt(picked)]
        : [el("p", { textContent: `Movie #${state.session.picked_movie_id}` })]),
    );
    return;
  }

  $("shortlist-empty").hidden = state.candidates.length > 0;
  $("shortlist").replaceChildren(
    ...state.candidates.map((movie) =>
      el(
        "li",
        { className: "shortlist-item" },
        poster(movie, "thumb", THUMB_URL),
        el(
          "div",
          { className: "title" },
          el("div", { textContent: movie.title }),
          el("div", { className: "muted", textContent: year(movie) }),
        ),
        el(
          "div",
          { className: "actions" },
          button("Pick", () => run(() => pickMovie(movie.id))),
          button("✕", () => run(() => removeCandidate(movie.id)), {
            className: "secondary",
            title: "Remove from shortlist",
            ariaLabel: `Remove ${movie.title} from shortlist`,
          }),
        ),
      ),
    ),
  );
}

// ---- Start ----

$("tab-search").addEventListener("click", () => showView("search"));
$("tab-library").addEventListener("click", () => showView("library"));

$("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  clearTimeout(searchTimer);
  search();
});
$("search-input").addEventListener("input", searchSoon);
$("search-by").addEventListener("change", () => {
  const by = $("search-by").value;
  $("search-input").placeholder = PLACEHOLDERS[by];
  $("role-filter").hidden = by !== "person";
  $("match-filter").hidden = by !== "keyword";
  search();
});
for (const id of ["role", "match", "genre", "language", "sort", "include-obscure", "include-upcoming"]) {
  $(id).addEventListener("change", () => search());
}

async function goToPage(page) {
  await search(page);
  $("tabs-top").scrollIntoView({ behavior: "smooth" });
}
$("page-prev").addEventListener("click", () => goToPage(state.page - 1));
$("page-next").addEventListener("click", () => goToPage(state.page + 1));
for (const id of ["year-from", "year-to"]) {
  $(id).addEventListener("input", searchSoon);
}
$("new-session").addEventListener("click", () => run(startNewSession));

document.addEventListener("click", closeStatusMenus);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeStatusMenus();
});

run(loadLibrary);
run(loadLatestSession);
run(loadGenres);
