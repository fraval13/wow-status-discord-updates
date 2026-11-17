'use strict';

// The main-window demo is set up once the page is parsed, so a fault in the
// preview below cannot stop it.
document.addEventListener('DOMContentLoaded', setupWindowDemo);

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
// A random line from pool, never the one shown just before.
function pickFlavour(pool, previous) {
  let index = Math.floor(Math.random() * pool.length);
  if (pool.length > 1 && pool[index] === previous) index = (index + 1) % pool.length;
  return pool[index];
}
function randomFlavour(kind) {
  previousFlavour[kind] = pickFlavour(window.WoWStatusFlavour[kind], previousFlavour[kind]);
  return previousFlavour[kind];
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
  const tabs = tablist ? [...tablist.querySelectorAll('[role="tab"]')] : [];
  const panels = tabs.map(tab => document.getElementById(tab.getAttribute('aria-controls')));
  const sortButton = document.querySelector('#demo-sort');
  const board = document.querySelector('.demo-board tbody');
  const onlineOnly = document.querySelector('#demo-online-only');
  const sections = [...document.querySelectorAll('#demo-characters .demo-section')]
    .map(button => [button, document.getElementById(button.getAttribute('aria-controls'))]);
  const players = [...document.querySelectorAll('#demo-characters .demo-cards')]
    .map(list => [list, list.previousElementSibling]);
  // Markup that no longer matches leaves the still picture as it is.
  if (tabs.length === 0 || panels.includes(null) || !sortButton || !board || !onlineOnly
    || sections.some(([, body]) => !body) || players.some(([, heading]) => !heading || !heading.dataset.player)) return;
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
      if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
      const last = tabs.length - 1;
      const next = { ArrowRight: index === last ? 0 : index + 1, ArrowLeft: index === 0 ? last : index - 1, Home: 0, End: last }[event.key];
      if (next === undefined) return;
      event.preventDefault();
      selectTab(next, true);
    });
  });
  // The panels become tab panels only now, so without JavaScript the Activity
  // page is plain content rather than a tab panel with no tabs.
  panels.forEach((panel, i) => {
    panel.setAttribute('role', 'tabpanel');
    panel.setAttribute('aria-labelledby', tabs[i].id);
  });
  tablist.hidden = false;

  // Captions from the same banks as the notifications, fresh on each visit. A
  // friend who is not your target or in your party gets the general death lines
  // in the game, so the demo leaves the class roasts out.
  document.querySelectorAll('.demo-flavour[data-bank]').forEach(line => {
    const bank = (window.WoWStatusFlavour || {})[line.dataset.bank];
    if (!Array.isArray(bank) || bank.length === 0) return;
    const pool = bank.map(text => text.match(/^\[([A-Z]+)\] (.+)$/) || [null, null, text])
      .filter(match => match[1] === null || match[1] === 'ANY')
      .map(match => match[2]);
    if (pool.length > 0) line.textContent = pickFlavour(pool, line.textContent);
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
  const headers = [...document.querySelectorAll('.demo-board th[data-sort]')];
  let sortIndex = 0;
  function sortBoard() {
    const by = sorts[sortIndex][0];
    // Highest first and XP breaks a level tie, as in Leaderboard.lua; then by name.
    const value = (row, key) => Number(row.dataset[key]);
    const rows = [...board.rows].sort((a, b) => value(b, by) - value(a, by)
      || (by === 'level' ? value(b, 'xp') - value(a, 'xp') : 0)
      || a.dataset.name.localeCompare(b.dataset.name));
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
  sections.forEach(([button, body]) => {
    button.disabled = false;
    button.addEventListener('click', () => {
      const open = button.getAttribute('aria-expanded') !== 'true';
      button.setAttribute('aria-expanded', String(open));
      body.hidden = !open;
    });
  });
  function filterCharacters() {
    players.forEach(([list, heading]) => {
      let visible = 0;
      list.querySelectorAll('.demo-card').forEach(card => {
        card.hidden = onlineOnly.checked && card.dataset.online !== 'true';
        if (!card.hidden) visible += 1;
      });
      // A player's heading counts the cards under it and goes when none are left.
      heading.hidden = visible === 0;
      list.hidden = visible === 0;
      heading.textContent = `${heading.dataset.player} (${visible} ${visible === 1 ? 'character' : 'characters'})`;
    });
  }
  onlineOnly.disabled = false;
  onlineOnly.addEventListener('change', filterCharacters);
  // A browser may restore the box ticked on reload without a change event.
  filterCharacters();
}

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
