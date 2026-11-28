-- Chạy một lần trong SQL Editor của dự án Supabase dành cho website này.
begin;

create table if not exists public.tn_admins (
  user_id uuid primary key references auth.users(id) on delete cascade
);
alter table public.tn_admins enable row level security;
revoke all on public.tn_admins from anon, authenticated;
grant select on public.tn_admins to authenticated;
create policy tn_admin_self_read on public.tn_admins for select to authenticated using (user_id = (select auth.uid()));

create or replace function public.tn_is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists(select 1 from public.tn_admins where user_id = (select auth.uid()));
$$;
revoke all on function public.tn_is_admin() from public;
grant execute on function public.tn_is_admin() to anon, authenticated;

create table if not exists public.tn_posts (
  id uuid primary key default gen_random_uuid(),
  title text not null check (length(btrim(title)) between 1 and 160),
  description text not null check (length(btrim(description)) between 1 and 10000),
  images text[] not null default '{}' check (cardinality(images) <= 8),
  status text not null default 'draft' check (status in ('draft', 'published', 'archived')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  published_at timestamptz
);
create index if not exists tn_posts_published on public.tn_posts (published_at desc, id desc) where status = 'published';
alter table public.tn_posts enable row level security;
revoke all on public.tn_posts from anon, authenticated;
grant select on public.tn_posts to anon;
grant select, insert, update on public.tn_posts to authenticated;
create policy tn_post_read on public.tn_posts for select to anon, authenticated using (status = 'published' or (select public.tn_is_admin()));
create policy tn_post_insert on public.tn_posts for insert to authenticated with check ((select public.tn_is_admin()));
create policy tn_post_update on public.tn_posts for update to authenticated using ((select public.tn_is_admin())) with check ((select public.tn_is_admin()));

create or replace function public.tn_stamp_post() returns trigger
language plpgsql set search_path = '' as $$
begin
  new.updated_at := now();
  if tg_op = 'UPDATE' then
    new.created_at := old.created_at;
    new.published_at := old.published_at;
  else
    new.created_at := now();
    new.published_at := null;
  end if;
  if new.status = 'published' and new.published_at is null then new.published_at := now(); end if;
  return new;
end;
$$;
create trigger tn_post_stamp before insert or update on public.tn_posts for each row execute function public.tn_stamp_post();

-- Public chỉ được đọc ảnh. Chỉ admin mới có quyền tải ảnh lên.
insert into storage.buckets(id, name, public, file_size_limit, allowed_mime_types)
values ('tn-post-images', 'tn-post-images', true, 5242880, array['image/jpeg','image/png','image/webp'])
on conflict (id) do nothing;
create policy tn_images_admin_insert on storage.objects for insert to authenticated with check (
  bucket_id = 'tn-post-images' and (select public.tn_is_admin())
  and (storage.foldername(name))[1] = (select auth.uid())::text
  and lower(storage.extension(name)) in ('jpg','png','webp')
);
create policy tn_images_admin_read on storage.objects for select to authenticated using (bucket_id = 'tn-post-images' and (select public.tn_is_admin()));

-- UUID trình duyệt ngẫu nhiên; không lưu IP, tên, email của khách.
create table if not exists public.tn_visitors (
  id uuid primary key,
  first_seen timestamptz not null default now()
);
create table if not exists public.tn_visit_days (
  visitor_id uuid not null references public.tn_visitors(id) on delete cascade,
  visit_date date not null,
  primary key(visitor_id, visit_date)
);
create index if not exists tn_visit_date on public.tn_visit_days(visit_date);
alter table public.tn_visitors enable row level security;
alter table public.tn_visit_days enable row level security;
revoke all on public.tn_visitors, public.tn_visit_days from anon, authenticated;

create or replace function public.tn_visit_stats() returns jsonb
language sql stable security definer set search_path = '' as $$
  select jsonb_build_object(
    'visitors', (select count(*) from public.tn_visitors),
    'today', (select count(*) from public.tn_visit_days where visit_date = (now() at time zone 'Asia/Ho_Chi_Minh')::date)
  );
$$;
create or replace function public.tn_record_visit(visitor_id uuid) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if visitor_id is null or visitor_id = '00000000-0000-0000-0000-000000000000'::uuid then
    raise exception 'Invalid visitor ID';
  end if;
  insert into public.tn_visitors(id) values (visitor_id) on conflict do nothing;
  insert into public.tn_visit_days(visitor_id, visit_date)
  values (visitor_id, (now() at time zone 'Asia/Ho_Chi_Minh')::date) on conflict do nothing;
  return public.tn_visit_stats();
end;
$$;
revoke all on function public.tn_visit_stats(), public.tn_record_visit(uuid) from public;
grant execute on function public.tn_visit_stats(), public.tn_record_visit(uuid) to anon, authenticated;
commit;

-- Sau khi tạo admin tại Authentication > Users, chạy riêng câu dưới
-- (thay email bằng email tài khoản thật; KHÔNG điền mật khẩu vào SQL):
-- insert into public.tn_admins(user_id)
-- select id from auth.users where email = 'EMAIL_ADMIN_CUA_BAN' on conflict do nothing;
