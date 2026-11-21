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
  view: "search", // "search" | "library" | "bracket"
  libraryFilter: "all", // a LIBRARY_FILTERS key
  session: null,
  candidates: [],
  examples: [], // [{ movie, positive }]: what tonight is, and isn't, about
  settingMood: false, // while on, movie cards mark examples instead of adding to the shortlist
  results: [],
  page: 1,
  totalPages: 1,
  library: [], // [{ movie, seen, intent, updated_at }], most recently changed first
  topic: "Better movie", // bracket topic
  bracket: null, // { topic, round, pairs, match, winners, reserves, champion } while one is played
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

const exampleOf = (movieId) => state.examples.find((example) => example.movie.id === movieId);

// While setting the mood: "Like this" / "Not this" toggles. Pressing the active one takes it back.
function moodActions(movie) {
  const current = exampleOf(movie.id)?.positive;
  const toggle = (label, positive) =>
    button(
      label,
      () => run(() => (current === positive ? removeExample(movie.id) : setExample(movie.id, positive))),
      { className: positive ? "like" : "not", ariaPressed: String(current === positive) },
    );
  return el("div", { className: "mood-actions" }, toggle("Like this", true), toggle("Not this", false));
}

function shortlistButton(movie) {
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
  return add;
}

function movieCard(movie) {

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
      state.settingMood && !isDecided() ? moodActions(movie) : shortlistButton(movie),
    ),
  );
}

function renderGrid() {
  $("movie-grid").hidden = state.view === "bracket";
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
  $("bracket-view").hidden = view !== "bracket";
  for (const name of ["search", "library", "bracket"]) $(`tab-${name}`).ariaPressed = String(view === name);
  renderGrid();
  if (view === "bracket") run(renderBracket);
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
  state.examples = detail.examples;
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

async function setExample(movieId, positive) {
  await api(`/sessions/${state.session.id}/examples`, { method: "PUT", body: { movie_id: movieId, positive } });
  await loadSession(state.session.id);
}

async function removeExample(movieId) {
  await api(`/sessions/${state.session.id}/examples/${movieId}`, { method: "DELETE" });
  await loadSession(state.session.id);
}

function setMoodOpen(open) {
  state.settingMood = open;
  renderSession();
  renderGrid();
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
  renderMood();

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
      sessionItem(
        movie,
        button("Pick", () => run(() => pickMovie(movie.id))),
        removeButton(`Remove ${movie.title} from shortlist`, () => removeCandidate(movie.id)),
      ),
    ),
  );
}

// The mood is context for suggestions, not a list to keep: closed, it's one line; open, the cards do the work.
function renderMood() {
  const likes = state.examples.filter((example) => example.positive).length;
  const nots = state.examples.length - likes;
  const counted = [likes && `${likes} like this`, nots && `${nots} not this`].filter(Boolean).join(" · ");
  const open = state.settingMood && !isDecided();

  $("mood").hidden = isDecided();
  $("mood-closed").hidden = open;
  $("mood-open-panel").hidden = !open;
  $("mood-summary").textContent = counted ? `Mood: ${counted}` : "";
  $("mood-open").textContent = counted ? "Change" : "Set tonight's mood";
  $("mood-count").textContent = counted || "Nothing marked yet";
}

function sessionItem(movie, ...actions) {
  return el(
    "li",
    { className: "shortlist-item" },
    poster(movie, "thumb", THUMB_URL),
    el(
      "div",
      { className: "title" },
      el("div", { textContent: movie.title }),
      el("div", { className: "muted", textContent: year(movie) }),
    ),
    el("div", { className: "actions" }, ...actions),
  );
}

function removeButton(label, remove) {
  return button("✕", () => run(remove), { className: "secondary", title: label, ariaLabel: label });
}

// ---- Bracket ----

// Topics about movies you've seen. Not trivia: there's no right answer, only yours.
const TOPICS = ["Better movie", "Better ending", "More fun to rewatch", "Stayed with me longer", "Better soundtrack"];

const isSeen = (movieId) => entryOf(movieId)?.seen ?? false;

async function startBracket() {
  const { pairs, reserves } = await api("/games/brackets", { method: "POST", body: { topic: state.topic } });
  state.bracket = { topic: state.topic, round: 1, pairs, match: 0, winners: [], reserves, champion: null };
  await renderBracket();
}

// While an answer is being saved, the match can't be answered again (no double-clicks).
async function answer(save) {
  for (const control of $("duel").querySelectorAll("button")) control.disabled = true;
  try {
    await save();
  } finally {
    await renderBracket();
  }
}

async function pickWinner(winner, loser) {
  await api("/games/comparisons", {
    method: "POST",
    body: { winner_id: winner.id, loser_id: loser.id, topic: state.bracket.topic },
  });
  advance(winner);
  await loadLibrary(); // both count as seen now
}

// "Haven't seen it": a stand-in takes its place. With none left, the other movie goes through.
async function notSeen(movie, side) {
  const bracket = state.bracket;
  await api("/games/not-seen", { method: "POST", body: { movie_id: movie.id, topic: bracket.topic } });
  const pair = bracket.pairs[bracket.match];
  const standIn = bracket.reserves.shift();
  if (standIn) pair[side] = standIn;
  else advance(pair[1 - side]);
}

// Record the match winner; after the last match of a round, pair the winners for the next one.
function advance(winner) {
  const bracket = state.bracket;
  bracket.winners.push(winner);
  bracket.match += 1;
  if (bracket.match < bracket.pairs.length) return;

  const winners = bracket.winners;
  if (winners.length === 1) {
    bracket.champion = winners[0];
    return;
  }
  const pairs = [];
  for (let i = 0; i < winners.length; i += 2) pairs.push([winners[i], winners[i + 1] ?? null]); // null: a bye
  Object.assign(bracket, { round: bracket.round + 1, pairs, match: 0, winners: [] });
}

function roundName(bracket) {
  if (bracket.pairs.length === 1) return "Final";
  if (bracket.pairs.length === 2) return "Semi-final";
  return `Round ${bracket.round}`;
}

async function renderBracket() {
  const bracket = state.bracket;
  const playing = Boolean(bracket) && !bracket.champion;
  if (playing && bracket.pairs[bracket.match][1] === null) {
    advance(bracket.pairs[bracket.match][0]); // the odd one out goes through on its own
    return renderBracket();
  }

  $("bracket-setup").hidden = Boolean(bracket);
  $("bracket-match").hidden = !playing;
  $("bracket-done").hidden = !bracket?.champion;

  if (!bracket) renderTopics();
  if (playing) {
    const pair = bracket.pairs[bracket.match];
    $("match-label").textContent = `${roundName(bracket)} · match ${bracket.match + 1} of ${bracket.pairs.length}`;
    $("match-topic").textContent = `${bracket.topic}?`;
    // Only first-round movies can be unseen: later ones have already played.
    $("duel").replaceChildren(...pair.map((movie, side) => contender(movie, pair[1 - side], side, bracket.round === 1)));
  }
  if (bracket?.champion) {
    const champion = bracket.champion;
    $("bracket-done").replaceChildren(
      el("p", { className: "label", textContent: `${bracket.topic}: the winner` }),
      poster(champion, "poster"),
      el("h3", { textContent: `${champion.title} (${year(champion)})` }),
      button("Play another", () => {
        state.bracket = null;
        run(renderBracket);
      }),
    );
  }
  await renderRankings(bracket?.topic ?? state.topic);
}

function contender(movie, opponent, side, canSkip) {
  const pick = button("", () => run(() => answer(() => pickWinner(movie, opponent))), {
    className: "contender-pick",
    ariaLabel: `${movie.title} wins`,
    title: `${movie.title} wins`,
  });
  pick.append(poster(movie, "poster"));
  return el(
    "div",
    { className: "contender" },
    pick,
    el("h3", { textContent: movie.title }),
    el("p", { className: "muted", textContent: year(movie) }),
    ...(canSkip && !isSeen(movie.id)
      ? [button("Haven't seen it", () => run(() => answer(() => notSeen(movie, side))), { className: "secondary" })]
      : []),
  );
}

function renderTopics() {
  $("topics").replaceChildren(
    ...TOPICS.map((topic) =>
      button(
        topic,
        () => {
          state.topic = topic;
          $("custom-topic").value = "";
          run(renderBracket);
        },
        { className: "chip", ariaPressed: String(state.topic === topic) },
      ),
    ),
  );
  $("custom-topic").value = TOPICS.includes(state.topic) ? "" : state.topic;
}

// Each row: the dot is the best guess, the band is roughly 95% sure. All rows share one scale so
// they can be compared. Only differences mean anything, so no numbers are shown.
const BAND_RANGE = 3;

function bandPosition(value) {
  const clamped = Math.max(-BAND_RANGE, Math.min(BAND_RANGE, value));
  return ((clamped + BAND_RANGE) / (2 * BAND_RANGE)) * 100;
}

async function renderRankings(topic) {
  const ranked = await api(`/games/rankings?${new URLSearchParams({ topic })}`);
  $("rankings").hidden = ranked.length === 0;
  $("rankings-title").textContent = `Your rankings: ${topic}`;
  $("rankings-list").replaceChildren(
    ...ranked.map(({ movie, strength, sd, games }) => {
      const low = bandPosition(strength - 1.96 * sd);
      const high = bandPosition(strength + 1.96 * sd);
      const range = el("span", { className: "band-range" });
      range.style.left = `${low}%`;
      range.style.width = `${high - low}%`;
      const dot = el("span", { className: "band-dot" });
      dot.style.left = `${bandPosition(strength)}%`;
      return el(
        "li",
        { className: "ranking" },
        poster(movie, "thumb", THUMB_URL),
        el(
          "div",
          { className: "title" },
          el("div", { textContent: movie.title }),
          el("div", { className: "muted", textContent: `${games} ${games === 1 ? "game" : "games"}` }),
        ),
        el("div", { className: "band", title: "Dot: best guess. Band: how sure it is so far." }, range, dot),
      );
    }),
  );
}

// ---- Start ----

$("tab-search").addEventListener("click", () => showView("search"));
$("tab-library").addEventListener("click", () => showView("library"));
$("tab-bracket").addEventListener("click", () => showView("bracket"));
$("bracket-start").addEventListener("click", () => run(startBracket));
$("bracket-quit").addEventListener("click", () => {
  state.bracket = null;
  run(renderBracket);
});
$("custom-topic-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const topic = $("custom-topic").value.trim();
  if (topic) state.topic = topic;
  run(renderBracket);
});

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
$("mood-open").addEventListener("click", () => setMoodOpen(true));
$("mood-close").addEventListener("click", () => setMoodOpen(false));

document.addEventListener("click", closeStatusMenus);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeStatusMenus();
});

run(loadLibrary);
run(loadLatestSession);
run(loadGenres);
