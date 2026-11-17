'use strict';

// The preview is deliberately local and illustrative, with no live player data.
const samples = [
  { kind: 'level', heading: 'LEVEL UP!', message: 'Thora reached level 33!', icon: 'level', color: '#ebc25e' },
  { kind: 'loot', heading: 'EPIC ARMOR EQUIPPED!', message: 'Eldrin equipped Robe of the Archmage', icon: 'armor', color: '#cb93f2' },
  { kind: 'profession-learned', heading: 'PROFESSION LEARNED!', message: 'Mira learned Blacksmithing (Apprentice)', icon: 'blacksmithing', color: '#80cfdf' },
  { kind: 'introduction', heading: 'WELCOME, ADVENTURER!', message: 'Thora joined the WoW Status group', icon: 'quests', color: '#e5c78e' },
];
const toast = document.querySelector('#demo-toast');
const controls = [...document.querySelectorAll('[data-preview]')];
let current = 0;
const previousFlavour = {};
function randomFlavour(kind) {
  const bank = window.WoWStatusFlavour[kind];
  let index = Math.floor(Math.random() * bank.length);
  if (bank.length > 1 && bank[index] === previousFlavour[kind]) index = (index + 1) % bank.length;
  previousFlavour[kind] = bank[index];
  return bank[index];
}
function showPreview(index) {
  current = index;
  const sample = samples[index];
  document.querySelector('#toast-flavour').textContent = randomFlavour(sample.kind);
  document.querySelector('#toast-heading').textContent = sample.heading;
  document.querySelector('#toast-heading').style.color = sample.color;
  document.querySelector('#toast-message').textContent = sample.message;
  document.querySelector('#toast-icon').src = `/assets/icons/${sample.icon}.jpg`;
  controls.forEach((button, i) => {
    button.classList.toggle('selected', i === index);
    button.setAttribute('aria-pressed', String(i === index));
  });
}
controls.forEach(button => button.addEventListener('click', () => showPreview(Number(button.dataset.preview))));
toast.addEventListener('click', () => showPreview((current + 1) % samples.length));

showPreview(0);

// The main-window demo (#195): invented characters drawn in the page itself.
// Without JavaScript the Activity page stays as a still picture; this adds the
// tab row, the filters, the leaderboard's sort and fresh captions.
function setupWindowDemo() {
  const tablist = document.querySelector('.wow-tabs');
  if (!tablist) return;
  const tabs = [...tablist.querySelectorAll('[role="tab"]')];
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
  function selectTab(index, focus) {
    tabs.forEach((tab, i) => {
      const chosen = i === index;
      tab.setAttribute('aria-selected', String(chosen));
      tab.tabIndex = chosen ? 0 : -1;
      panels[i].hidden = !chosen;
    });
    if (focus) tabs[index].focus();
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => selectTab(index, false));
    tab.addEventListener('keydown', event => {
      const last = tabs.length - 1;
      const next = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      selectTab(next, true);
    });
  });
  tablist.hidden = false;

  // Captions from the same banks as the notifications. A death draws from the
  // general lines and the fallen character's own class, as in the game.
  document.querySelectorAll('.demo-flavour[data-bank]').forEach(line => {
    const bank = (window.WoWStatusFlavour || {})[line.dataset.bank];
    if (!Array.isArray(bank) || bank.length === 0) return;
    const tags = ['ANY', line.dataset.class].filter(Boolean);
    const pool = bank.map(text => text.match(/^\[([A-Z]+)\] (.+)$/) || [null, null, text])
      .filter(match => match[1] === null || tags.includes(match[1]))
      .map(match => match[2]);
    if (pool.length > 0) line.textContent = pool[Math.floor(Math.random() * pool.length)];
  });

  // Activity: All, Mine and Friends, as at the bottom of the real page.
  const entries = [...document.querySelectorAll('#demo-activity .demo-entry')];
  const filters = [...document.querySelectorAll('#demo-activity [data-filter]')];
  function filterActivity(which) {
    entries.forEach(entry => {
      const mine = entry.dataset.mine === 'true';
      entry.hidden = (which === 'mine' && !mine) || (which === 'friends' && mine);
    });
    filters.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === which)));
  }
  filters.forEach(button => {
    button.disabled = false;
    button.addEventListener('click', () => filterActivity(button.dataset.filter));
  });

  // Leaderboard: the Sort button steps through the same four orders as the addon.
  const sorts = [['level', 'Level'], ['deaths', 'Deaths'], ['quests', 'Quests'], ['played', 'Played time']];
  const sortButton = document.querySelector('#demo-sort');
  const board = document.querySelector('.demo-board tbody');
  const headers = [...document.querySelectorAll('.demo-board th[data-sort]')];
  let sortIndex = 0;
  function sortBoard() {
    const by = sorts[sortIndex][0];
    const value = row => by === 'level'
      ? Number(row.dataset.level) * 1000 + Number(row.dataset.xp)
      : Number(row.dataset[by]);
    const rows = [...board.rows].sort((a, b) => value(b) - value(a) || a.dataset.name.localeCompare(b.dataset.name));
    rows.forEach((row, i) => {
      row.cells[0].textContent = `${i + 1}.`;
      board.appendChild(row);
    });
    headers.forEach(header => {
      if (header.dataset.sort === by) header.setAttribute('aria-sort', 'descending');
      else header.removeAttribute('aria-sort');
    });
    sortButton.textContent = `Sort: ${sorts[sortIndex][1]}`;
  }
  sortButton.disabled = false;
  sortButton.addEventListener('click', () => {
    sortIndex = (sortIndex + 1) % sorts.length;
    sortBoard();
  });

  // Characters: collapsible sections and the Online only filter.
  document.querySelectorAll('#demo-characters .demo-section').forEach(button => {
    const body = document.getElementById(button.getAttribute('aria-controls'));
    button.disabled = false;
    button.addEventListener('click', () => {
      const open = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', String(open));
      body.hidden = !open;
    });
  });
  const onlineOnly = document.querySelector('#demo-online-only');
  onlineOnly.disabled = false;
  onlineOnly.addEventListener('change', () => {
    document.querySelectorAll('#demo-characters .demo-cards').forEach(list => {
      let visible = 0;
      list.querySelectorAll('.demo-card').forEach(card => {
        card.hidden = onlineOnly.checked && card.dataset.online !== 'true';
        if (!card.hidden) visible += 1;
      });
      // A player's heading counts the cards under it and goes when none are left.
      const heading = list.previousElementSibling;
      heading.hidden = visible === 0;
      list.hidden = visible === 0;
      heading.textContent = `${heading.dataset.player} (${visible} ${visible === 1 ? 'character' : 'characters'})`;
    });
  });
}
setupWindowDemo();

// Keep navigation useful on long pages without a router or external scripts.
const topLinks = [...document.querySelectorAll('.top-nav a')];
const sideLinks = [...document.querySelectorAll('.menu-panel a')];
function updateNavigation() {
  const target = location.hash || '#home';
  topLinks.forEach(link => link.classList.toggle('active', link.getAttribute('href') === target));
  sideLinks.forEach(link => link.classList.toggle('current', link.getAttribute('href') === target));
}
window.addEventListener('hashchange', updateNavigation);
updateNavigation();
