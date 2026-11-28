import { configured, signIn, signOut, restoreAdmin, adminRequest, uploadImage, imageUrl, getStats, element, formatNumber, formatDate } from '../assets/data.js';
const $ = id => document.getElementById(id);
const statusNames = { published: 'Đã đăng', draft: 'Bản nháp', archived: 'Đã ẩn' };
let id = crypto.randomUUID(), images = [], page = 0, dirty = false, busy = false;
function message(target, text = '', kind = '') { $(target).textContent = text; $(target).className = `message ${kind}`; }
function setBusy(value) {
  busy = value;
  for (const el of document.querySelectorAll('#post-form input,#post-form textarea,#post-form select,#post-form button,#new-post,#logout,.row-actions button')) el.disabled = value;
}
function releaseImages() { for (const image of images) if (image.file) URL.revokeObjectURL(image.url); }
function resetEditor() {
  releaseImages(); images = []; id = crypto.randomUUID(); dirty = false;
  $('post-form').reset(); $('editor-title').textContent = 'Viết bài mới'; message('post-message'); $('saving-progress').textContent = ''; renderImages();
}
function mayDiscard() { return !dirty || confirm('Bạn đang có thay đổi chưa lưu. Bỏ thay đổi này?'); }
function renderImages() {
  $('image-count').textContent = `${images.length} / 8 ảnh`;
  $('image-previews').replaceChildren(...images.map((image, index) => {
    const figure = element('figure', 'image-preview');
    const img = element('img'); img.src = image.url; img.alt = `Ảnh bài viết ${index + 1}`;
    const remove = element('button', '', 'Bỏ ảnh'); remove.type = 'button'; remove.disabled = busy; remove.setAttribute('aria-label', `Bỏ ảnh ${index + 1}`);
    remove.addEventListener('click', () => { if (image.file) URL.revokeObjectURL(image.url); images.splice(index, 1); dirty = true; renderImages(); });
    figure.append(img, element('figcaption', '', index === 0 ? 'Ảnh bìa' : `Ảnh ${index + 1}`), remove); return figure;
  }));
}
async function refreshStats() {
  $('refresh-stats').disabled = true;
  message('stats-message');
  try { const stats = await getStats(); $('stats-total').textContent = formatNumber(stats.visitors); $('stats-today').textContent = formatNumber(stats.today); }
  catch (error) { message('stats-message', error.message, 'error'); }
  finally { $('refresh-stats').disabled = false; }
}
function edit(post) {
  if (busy || !mayDiscard()) return;
  releaseImages(); id = post.id;
  $('title').value = post.title; $('description').value = post.description; $('status').value = post.status;
  images = post.images.filter(path => imageUrl(path)).map(path => ({ path, url: imageUrl(path) }));
  $('editor-title').textContent = 'Chỉnh sửa bài viết'; message('post-message'); dirty = false; renderImages(); $('title').focus();
}
async function changeStatus(post, button) {
  if (busy) return;
  const next = post.status === 'published' ? 'archived' : 'published';
  setBusy(true);
  try {
    const rows = await adminRequest(`/rest/v1/tn_posts?id=eq.${post.id}`, { method: 'PATCH', body: { status: next }, headers: { Prefer: 'return=representation' } });
    if (!rows?.length) throw new Error('Không cập nhật được bài viết. Vui lòng tải lại danh sách.');
    if (id === post.id) $('status').value = next;
    await loadPosts();
  } catch (error) { message('posts-message', error.message, 'error'); }
  finally { setBusy(false); }
}
async function loadPosts() {
  $('refresh-posts').disabled = true;
  message('posts-message', 'Đang tải bài viết…');
  try {
    const posts = await adminRequest(`/rest/v1/tn_posts?select=*&order=created_at.desc,id.desc&limit=12&offset=${page * 12}`);
    $('post-list').replaceChildren(...posts.map(post => {
      const row = element('article', 'post-row');
      const meta = element('div', 'post-meta'); meta.append(element('span', `badge ${post.status}`, statusNames[post.status]), element('time', '', formatDate(post.created_at)));
      const actions = element('div', 'row-actions');
      const editButton = element('button', 'text-button', 'Chỉnh sửa'); editButton.type = 'button'; editButton.disabled = busy; editButton.addEventListener('click', () => edit(post));
      const toggleButton = element('button', 'text-button', post.status === 'published' ? 'Ẩn bài' : 'Đăng công khai'); toggleButton.type = 'button'; toggleButton.disabled = busy; toggleButton.addEventListener('click', () => changeStatus(post, toggleButton));
      actions.append(editButton, toggleButton); row.append(meta, element('h3', '', post.title), element('p', '', post.description), actions); return row;
    }));
    message('posts-message', posts.length ? '' : 'Chưa có bài viết. Bạn có thể viết bài đầu tiên ở khung bên cạnh.');
    $('previous-page').disabled = page === 0; $('next-page').disabled = posts.length < 12; $('page-label').textContent = `Trang ${page + 1}`;
  } catch (error) { message('posts-message', error.message, 'error'); }
  finally { $('refresh-posts').disabled = false; }
}
async function showDashboard(user) {
  $('login-panel').hidden = true; $('dashboard').hidden = false; $('account').textContent = user.email;
  await Promise.all([loadPosts(), refreshStats()]);
}
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); $('login-button').disabled = true; message('login-message', 'Đang đăng nhập…');
  try { const user = await signIn($('email').value.trim(), $('password').value); $('password').value = ''; await showDashboard(user); }
  catch (error) { message('login-message', error.status === 400 ? 'Email hoặc mật khẩu chưa đúng.' : error.message, 'error'); }
  finally { $('login-button').disabled = !configured; }
});
$('logout').addEventListener('click', async () => {
  if (busy || !mayDiscard()) return;
  try { await signOut(); } catch { /* Local credentials are cleared even if the network fails. */ }
  resetEditor(); $('dashboard').hidden = true; $('login-panel').hidden = false; $('post-list').replaceChildren(); message('login-message', 'Đã đăng xuất.');
});
$('post-form').addEventListener('input', () => { dirty = true; });
$('images').addEventListener('change', async event => {
  const files = Array.from(event.target.files);
  if (images.length + files.length > 8) { message('post-message', 'Mỗi bài tối đa 8 ảnh. Vui lòng chọn ít ảnh hơn.', 'error'); event.target.value = ''; return; }
  if (files.some(file => !['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024)) { message('post-message', 'Chỉ nhận ảnh JPG, PNG, WebP; mỗi ảnh tối đa 5 MB.', 'error'); event.target.value = ''; return; }
  const valid = [];
  setBusy(true);
  try {
    for (const file of files) { const decoded = await createImageBitmap(file); decoded.close(); valid.push({ file, url: URL.createObjectURL(file) }); }
    images.push(...valid); dirty = true; message('post-message'); renderImages();
  } catch { for (const item of valid) URL.revokeObjectURL(item.url); message('post-message', 'Có tệp không đọc được như ảnh. Vui lòng chọn ảnh khác.', 'error'); }
  finally { event.target.value = ''; setBusy(false); }
});
$('post-form').addEventListener('submit', async event => {
  event.preventDefault();
  if (busy) return;
  const title = $('title').value.trim(), description = $('description').value.trim(), status = $('status').value;
  if (!title || !description) { message('post-message', 'Vui lòng nhập tiêu đề và mô tả.', 'error'); return; }
  setBusy(true); message('post-message');
  try {
    for (const [index, image] of images.entries()) {
      if (!image.path) { $('saving-progress').textContent = `Đang tải ảnh ${index + 1}/${images.length}…`; image.path = await uploadImage(image.file); }
    }
    $('saving-progress').textContent = 'Đang lưu bài viết…';
    const result = await adminRequest('/rest/v1/tn_posts?on_conflict=id', { method: 'POST', body: { id, title, description, status, images: images.map(image => image.path) }, headers: { Prefer: 'resolution=merge-duplicates,return=representation' } });
    if (!result?.length) throw new Error('Chưa xác nhận được bài đã lưu. Vui lòng thử lại.');
    dirty = false; $('editor-title').textContent = 'Chỉnh sửa bài viết';
    message('post-message', status === 'published' ? 'Đã đăng bài. Bài viết đã có trên website.' : status === 'draft' ? 'Đã lưu bản nháp.' : 'Đã lưu và ẩn bài viết.', 'success');
    page = 0; await loadPosts();
  } catch (error) { message('post-message', error.message, 'error'); }
  finally { $('saving-progress').textContent = ''; setBusy(false); }
});
$('new-post').addEventListener('click', () => { if (!busy && mayDiscard()) { resetEditor(); $('title').focus(); } });
$('refresh-posts').addEventListener('click', loadPosts);
$('refresh-stats').addEventListener('click', refreshStats);
$('previous-page').addEventListener('click', () => { if (page > 0) { page--; loadPosts(); } });
$('next-page').addEventListener('click', () => { page++; loadPosts(); });
window.addEventListener('beforeunload', event => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } });
if (!configured) {
  $('setup-notice').hidden = false; $('login-button').disabled = true; $('email').disabled = true; $('password').disabled = true;
} else {
  $('login-button').disabled = true;
  restoreAdmin().then(user => { if (user) return showDashboard(user); }).catch(error => message('login-message', error.message, 'error')).finally(() => { $('login-button').disabled = false; });
}
