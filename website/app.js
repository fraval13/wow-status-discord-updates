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
