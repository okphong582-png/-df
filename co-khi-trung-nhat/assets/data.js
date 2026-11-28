import { siteConfig } from '../site-config.js';

function publicKey(key) {
  if (/^sb_publishable_[a-zA-Z0-9_-]+$/.test(key)) return true;
  try { return JSON.parse(atob(key.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))).role === 'anon'; } catch { return false; }
}
export const configured = /^https:\/\/[a-z0-9-]+\.supabase\.co$/i.test(siteConfig.supabaseUrl) && publicKey(siteConfig.supabaseKey);
const base = siteConfig.supabaseUrl.replace(/\/$/, '');
const sessionKey = 'tn-admin-session';
let session = null;
try { session = JSON.parse(sessionStorage.getItem(sessionKey) || 'null'); } catch { /* Storage may be disabled. */ }
let refreshing;

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}
export function clearSession() {
  session = null;
  try { sessionStorage.removeItem(sessionKey); } catch { /* No persistent session. */ }
}
function saveSession(value) {
  session = { access_token: value.access_token, refresh_token: value.refresh_token, expires_at: Date.now() + value.expires_in * 1000, user: value.user };
  try { sessionStorage.setItem(sessionKey, JSON.stringify(session)); } catch { /* Session stays in memory. */ }
}
async function request(path, { method = 'GET', body, token, headers = {} } = {}) {
  if (!configured) throw new ApiError('Chưa kết nối kho dữ liệu. Vui lòng hoàn tất cấu hình Supabase.', 503);
  const abort = new AbortController();
  const timeout = setTimeout(() => abort.abort(), 25000);
  try {
    const response = await fetch(base + path, {
      method, signal: abort.signal, cache: 'no-store',
      headers: { apikey: siteConfig.supabaseKey, ...(token ? { Authorization: `Bearer ${token}` } : siteConfig.supabaseKey.startsWith('eyJ') ? { Authorization: `Bearer ${siteConfig.supabaseKey}` } : {}), ...(body && !(body instanceof Blob) ? { 'Content-Type': 'application/json' } : {}), ...headers },
      body: body instanceof Blob ? body : body === undefined ? undefined : JSON.stringify(body),
    });
    const result = await response.text();
    let value;
    try { value = result ? JSON.parse(result) : null; } catch { value = null; }
    if (!response.ok) {
      const message = response.status === 401 ? 'Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.'
        : response.status === 403 ? 'Tài khoản chưa được cấp quyền quản trị.'
        : response.status === 413 ? 'Ảnh quá lớn. Mỗi ảnh tối đa 5 MB.'
        : response.status === 429 ? 'Bạn thao tác quá nhanh. Vui lòng thử lại sau.'
        : 'Không thực hiện được thao tác. Vui lòng kiểm tra kết nối hoặc cấu hình dữ liệu.';
      throw new ApiError(message, response.status);
    }
    return value;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    throw new ApiError('Không kết nối được máy chủ. Vui lòng kiểm tra mạng rồi thử lại.', 0);
  } finally { clearTimeout(timeout); }
}
export async function adminRequest(path, options = {}) {
  if (!session) throw new ApiError('Vui lòng đăng nhập để tiếp tục.', 401);
  if (session.expires_at < Date.now() + 60000) {
    if (!refreshing) refreshing = request('/auth/v1/token?grant_type=refresh_token', { method: 'POST', body: { refresh_token: session.refresh_token } })
      .then(saveSession).catch(error => { clearSession(); throw error; }).finally(() => { refreshing = null; });
    await refreshing;
  }
  return request(path, { ...options, token: session.access_token });
}
export async function signIn(email, password) {
  const value = await request('/auth/v1/token?grant_type=password', { method: 'POST', body: { email, password } });
  saveSession(value);
  try {
    if (!await adminRequest('/rest/v1/rpc/tn_is_admin', { method: 'POST', body: {} })) throw new ApiError('Tài khoản này chưa được cấp quyền quản trị.', 403);
  } catch (error) { await signOut(); throw error; }
  return session.user;
}
export async function restoreAdmin() {
  if (!session) return null;
  if (!await adminRequest('/rest/v1/rpc/tn_is_admin', { method: 'POST', body: {} })) { clearSession(); return null; }
  return session?.user;
}
export async function signOut() {
  try { if (session) await request('/auth/v1/logout', { method: 'POST', token: session.access_token }); }
  finally { clearSession(); }
}
export function imageUrl(path) {
  if (!/^[a-f0-9-]{36}\/[a-f0-9-]{36}\.(jpg|png|webp)$/i.test(path)) return '';
  return `${base}/storage/v1/object/public/tn-post-images/${path}`;
}
export async function uploadImage(file) {
  const ext = { 'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp' }[file.type];
  if (!ext || file.size > 5 * 1024 * 1024) throw new ApiError('Chỉ nhận ảnh JPG, PNG, WebP và tối đa 5 MB/ảnh.', 400);
  const path = `${session.user.id}/${crypto.randomUUID()}.${ext}`;
  await adminRequest('/storage/v1/object/tn-post-images/' + path, { method: 'POST', body: file, headers: { 'Content-Type': file.type, 'x-upsert': 'false', 'Cache-Control': 'max-age=31536000' } });
  return path;
}
export const listPosts = (offset = 0) => request(`/rest/v1/tn_posts?select=id,title,description,images,published_at&status=eq.published&order=published_at.desc,id.desc&limit=6&offset=${offset}`);
export const getStats = () => request('/rest/v1/rpc/tn_visit_stats', { method: 'POST', body: {} });
export async function recordVisit() {
  let visitor;
  // If storage is blocked, do not mint a new visitor on every page load.
  try {
    visitor = localStorage.getItem('tn-visitor-id');
    if (!/^[a-f0-9-]{36}$/i.test(visitor || '')) { visitor = crypto.randomUUID(); localStorage.setItem('tn-visitor-id', visitor); }
  } catch { return getStats(); }
  return request('/rest/v1/rpc/tn_record_visit', { method: 'POST', body: { visitor_id: visitor } });
}
export function element(tag, className, text) {
  const el = document.createElement(tag);
  if (className) el.className = className;
  if (text !== undefined) el.textContent = text;
  return el;
}
export const formatNumber = value => new Intl.NumberFormat('vi-VN').format(value);
export const formatDate = value => new Intl.DateTimeFormat('vi-VN', { dateStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value));
