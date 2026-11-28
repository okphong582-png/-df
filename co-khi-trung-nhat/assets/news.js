import { configured, listPosts, recordVisit, imageUrl, element, formatDate, formatNumber } from './data.js';

const section = document.querySelector('#tin-moi');
const grid = document.querySelector('#news-grid');
const more = document.querySelector('#news-more');
const message = document.querySelector('#news-message');
const dialog = document.querySelector('#post-dialog');
const body = document.querySelector('#post-body');
let offset = 0;
let opener;

function openPost(post, trigger) {
  opener = trigger;
  body.replaceChildren();
  body.append(element('time', 'news-date', formatDate(post.published_at)), element('h2', '', post.title), element('p', 'post-description', post.description));
  const gallery = element('div', 'post-images');
  for (const [index, path] of post.images.entries()) {
    const src = imageUrl(path);
    if (!src) continue;
    const img = element('img'); img.src = src; img.alt = `${post.title} — ảnh ${index + 1}`; img.loading = 'lazy';
    gallery.append(img);
  }
  body.append(gallery);
  dialog.showModal();
  document.body.style.overflow = 'hidden';
}
function card(post) {
  const article = element('article', 'news-card');
  const cover = post.images.map(imageUrl).find(Boolean);
  if (cover) { const img = element('img', 'news-cover'); img.src = cover; img.alt = post.title; img.loading = 'lazy'; article.append(img); }
  const content = element('div', 'news-card-body');
  const date = element('time', 'news-date', formatDate(post.published_at)); date.dateTime = post.published_at;
  const button = element('button', 'news-open', 'Xem bài viết'); button.type = 'button'; button.setAttribute('aria-label', `Xem bài viết: ${post.title}`);
  button.addEventListener('click', () => openPost(post, button));
  content.append(date, element('h3', '', post.title), element('p', 'news-excerpt', post.description), button);
  article.append(content);
  return article;
}
async function load() {
  more.disabled = true;
  message.textContent = '';
  try {
    const posts = await listPosts(offset);
    if (posts.length) { grid.append(...posts.map(card)); section.hidden = false; }
    offset += posts.length;
    more.hidden = posts.length < 6;
  } catch {
    if (offset) message.textContent = 'Chưa tải được bài tiếp theo. Bạn có thể thử lại.';
  } finally { more.disabled = false; }
}
document.querySelector('#post-close').addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
dialog.addEventListener('close', () => { document.body.style.overflow = ''; opener?.focus(); });
more.addEventListener('click', load);
if (configured) {
  load();
  recordVisit().then(stats => {
    if (!Number.isSafeInteger(stats.visitors) || !Number.isSafeInteger(stats.today)) return;
    document.querySelector('#visitors-total').textContent = formatNumber(stats.visitors);
    document.querySelector('#visitors-today').textContent = formatNumber(stats.today);
    document.querySelector('#visitor-area').hidden = false;
  }).catch(() => { /* Do not display invented counts when offline. */ });
}
