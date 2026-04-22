// ── State ──────────────────────────────────────────────────────────────────
const state = {
  selectedCategory: null,
  selectedLabel: null,
  zipcode: '',
};

// ── DOM refs ───────────────────────────────────────────────────────────────
const screenHome    = document.getElementById('screen-home');
const screenResults = document.getElementById('screen-results');
const zipcodeInput  = document.getElementById('zipcode-input');
const zipcodeError  = document.getElementById('zipcode-error');
const searchBtn     = document.getElementById('search-btn');
const backBtn       = document.getElementById('back-btn');
const resultsTitle  = document.getElementById('results-title');
const resultsList   = document.getElementById('results-list');
const cardTemplate  = document.getElementById('result-card-template');

// ── Category selection ──────────────────────────────────────────────────────
document.querySelectorAll('.category-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    state.selectedCategory = btn.dataset.category;
    state.selectedLabel    = btn.dataset.label;
    updateSearchBtn();
  });
});

// ── Zipcode input ───────────────────────────────────────────────────────────
zipcodeInput.addEventListener('input', () => {
  // Strip non-digits
  zipcodeInput.value = zipcodeInput.value.replace(/\D/g, '').slice(0, 5);
  state.zipcode = zipcodeInput.value;
  zipcodeError.classList.add('hidden');
  updateSearchBtn();
});

function updateSearchBtn() {
  const ready = state.selectedCategory && state.zipcode.length === 5;
  searchBtn.disabled = !ready;
}

// ── Search ──────────────────────────────────────────────────────────────────
searchBtn.addEventListener('click', async () => {
  if (!validateZip()) return;
  showScreen(screenResults);
  resultsTitle.textContent = `${state.selectedLabel} near ${state.zipcode}`;
  await loadResults();
});

function validateZip() {
  if (!/^\d{5}$/.test(state.zipcode)) {
    zipcodeError.classList.remove('hidden');
    zipcodeInput.focus();
    return false;
  }
  return true;
}

// ── Back navigation ──────────────────────────────────────────────────────────
backBtn.addEventListener('click', () => showScreen(screenHome));

// ── Screen switching ─────────────────────────────────────────────────────────
function showScreen(screen) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  screen.classList.add('active');
  window.scrollTo(0, 0);
}

// ── Results loading ──────────────────────────────────────────────────────────
async function loadResults() {
  resultsList.innerHTML = '<p class="loading-msg">Looking for services nearby…</p>';

  try {
    const params = new URLSearchParams({
      zip:      state.zipcode,
      category: state.selectedCategory,
    });

    const res  = await fetch(`/api/search?${params}`);
    const data = await res.json();

    if (!res.ok) throw new Error(data.error || 'Server error');

    renderResults(data.results || []);
  } catch (err) {
    console.error(err);
    resultsList.innerHTML = `
      <p class="error-card">
        Something went wrong. Please check your connection and try again.
      </p>`;
  }
}

// ── Render ───────────────────────────────────────────────────────────────────
function renderResults(results) {
  resultsList.innerHTML = '';

  if (results.length === 0) {
    resultsList.innerHTML = `
      <p class="empty-msg">
        No results found near ${state.zipcode}.<br>Try a different zip code or category.
      </p>`;
    return;
  }

  results.forEach(place => {
    const card = cardTemplate.content.cloneNode(true);

    card.querySelector('.result-name').textContent = place.name;
    card.querySelector('.result-address').textContent = place.address || 'Address not available';

    const callBtn = card.querySelector('.btn-call');
    if (place.phone) {
      callBtn.href = `tel:${place.phone}`;
      callBtn.textContent = '📞 Call';
    } else {
      callBtn.textContent = 'No phone listed';
      callBtn.style.opacity = '.5';
      callBtn.style.pointerEvents = 'none';
    }

    // Opens Google Maps in transit mode — works as a deep link on iOS & Android
    const mapsUrl = `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(place.address)}&travelmode=transit`;
    card.querySelector('.btn-directions').href = mapsUrl;

    resultsList.appendChild(card);
  });
}
