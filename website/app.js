'use strict';

// The preview is deliberately local and illustrative, with no live player data.
const samples = [
  { heading: 'LEVEL UP!', message: 'Thora reached level 33!', icon: 'level', color: '#ebc25e' },
  { heading: 'EPIC ARMOR EQUIPPED!', message: 'Eldrin equipped Robe of the Archmage', icon: 'armor', color: '#cb93f2' },
  { heading: 'PROFESSION LEARNED!', message: 'Mira learned Blacksmithing (Apprentice)', icon: 'blacksmithing', color: '#80cfdf' },
  { heading: 'WELCOME, ADVENTURER!', message: 'Thora joined the group', icon: 'quests', color: '#e5c78e' },
];
const toast = document.querySelector('#demo-toast');
const controls = [...document.querySelectorAll('[data-preview]')];
let current = 0;
function showPreview(index) {
  current = index;
  const sample = samples[index];
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

// Opt-in artwork experiment. The normal URL remains the original still image.
// No preference is persisted: ?motion=on / ?motion=off are easy comparison links.
const motionMode = new URLSearchParams(location.search).get('motion');
if (motionMode === 'on' || motionMode === 'off') {
  const hero = document.querySelector('.hero');
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'hero-motion-toggle';
  hero.classList.add('motion-preview');
  hero.append(toggle);
  let video;
  let wanted = false;
  let visible = true;
  let playbackRequest = 0;

  function setMotion(enabled, updateURL = true) {
    wanted = enabled;
    toggle.textContent = enabled ? 'Still image' : 'Animated preview';
    toggle.setAttribute('aria-pressed', String(enabled));
    toggle.setAttribute('aria-label', enabled ? 'Show the original still image' : 'Play the animated artwork preview');
    if (updateURL) {
      const url = new URL(location.href);
      url.searchParams.set('motion', enabled ? 'on' : 'off');
      history.replaceState(null, '', url);
    }
    if (enabled && !video) {
      video = document.createElement('video');
      video.className = 'hero-motion';
      video.muted = true;
      video.loop = true;
      video.playsInline = true;
      video.preload = 'none';
      video.setAttribute('aria-hidden', 'true');
      video.setAttribute('disablepictureinpicture', '');
      for (const [file, type] of [['adventure-motion.webm', 'video/webm'], ['adventure-motion.mp4', 'video/mp4']]) {
        const source = document.createElement('source');
        source.src = `/assets/${file}`;
        source.type = type;
        video.append(source);
      }
      video.addEventListener('playing', () => video.classList.toggle('is-playing', wanted));
      video.addEventListener('error', () => setMotion(false));
      hero.prepend(video);
    }
    if (video && !enabled) video.classList.remove('is-playing');
    syncPlayback();
  }

  function syncPlayback() {
    if (!video) return;
    const request = ++playbackRequest;
    if (wanted && visible && !document.hidden) {
      video.play().catch(error => {
        if (wanted && request === playbackRequest && error.name !== 'AbortError') setMotion(false);
      });
    } else {
      video.pause();
    }
  }
  toggle.addEventListener('click', () => setMotion(!wanted));
  document.addEventListener('visibilitychange', syncPlayback);
  reducedMotion.addEventListener('change', event => { if (event.matches) setMotion(false); });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      syncPlayback();
    }).observe(hero);
  }
  setMotion(motionMode === 'on' && !reducedMotion.matches, false);
}
