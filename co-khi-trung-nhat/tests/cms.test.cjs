// Run: set TN_TEST_DEPS=<folder containing installed @electric-sql/pglite>
//      node --test tests/cms.test.cjs
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFile } = require('node:fs/promises');
const { createRequire } = require('node:module');
const path = require('node:path');
const { PGlite } = createRequire(path.join(process.env.TN_TEST_DEPS, 'package.json'))('@electric-sql/pglite');

test('CMS: database authorization, post visibility, storage policies and deduplicated visitors', async () => {
  const db = new PGlite();
  try {
    await db.exec(`
      create role anon; create role authenticated;
      create schema auth; create schema storage;
      create table auth.users(id uuid primary key, email text);
      create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
      grant usage on schema auth to anon, authenticated;
      grant execute on function auth.uid() to anon, authenticated;
      create table storage.buckets(id text primary key, name text, public boolean, file_size_limit bigint, allowed_mime_types text[]);
      create table storage.objects(id uuid default gen_random_uuid(), bucket_id text, name text);
      alter table storage.objects enable row level security;
      grant usage on schema storage to anon, authenticated;
      grant insert, select on storage.objects to anon, authenticated;
      create function storage.foldername(text) returns text[] language sql immutable as $$ select (string_to_array($1,'/'))[1:1] $$;
      create function storage.extension(text) returns text language sql immutable as $$ select regexp_replace($1, '^.*\\.', '') $$;
    `);
    await db.exec(await readFile(path.join(__dirname, '../supabase/setup.sql'), 'utf8'));
    const admin = '11111111-1111-4111-8111-111111111111';
    const visitor = '22222222-2222-4222-8222-222222222222';
    const stranger = '33333333-3333-4333-8333-333333333333';
    await db.query('insert into auth.users(id,email) values ($1,$2),($3,$4)', [admin,'admin@example.test',stranger,'other@example.test']);
    await db.query('insert into public.tn_admins(user_id) values ($1)', [admin]);
    async function as(role, uid = '') {
      await db.exec('reset role');
      await db.query("select set_config('request.jwt.claim.sub', $1, false)", [uid]);
      await db.exec(`set role ${role}`);
    }
    await as('anon');
    assert.equal((await db.query('select public.tn_is_admin() as value')).rows[0].value, false);
    await assert.rejects(db.query("insert into public.tn_posts(title,description) values ('X','Y')"));
    await assert.rejects(db.query('select * from public.tn_visitors'));
    await assert.rejects(db.query('select * from public.tn_admins'));
    const first = (await db.query('select public.tn_record_visit($1) as stats',[visitor])).rows[0].stats;
    assert.deepEqual(first, { visitors: 1, today: 1 });
    const repeated = (await db.query('select public.tn_record_visit($1) as stats',[visitor])).rows[0].stats;
    assert.deepEqual(repeated, { visitors: 1, today: 1 });
    await assert.rejects(db.query('select public.tn_record_visit(null)'));
    await as('authenticated', stranger);
    assert.equal((await db.query('select public.tn_is_admin() as value')).rows[0].value, false);
    await assert.rejects(db.query("insert into public.tn_posts(title,description) values ('X','Y')"));
    await assert.rejects(db.query('insert into public.tn_admins(user_id) values ($1)',[stranger]));
    await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values ('tn-post-images',$1)",[`${stranger}/test.jpg`]));
    await as('authenticated', admin);
    assert.equal((await db.query('select public.tn_is_admin() as value')).rows[0].value, true);
    const post = (await db.query("insert into public.tn_posts(title,description,status) values ('Ảnh công trình','Mô tả có dấu','draft') returning *")).rows[0];
    assert.equal(post.published_at, null);
    await db.query("insert into storage.objects(bucket_id,name) values ('tn-post-images',$1)",[`${admin}/test.jpg`]);
    await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values ('tn-post-images',$1)",[`${admin}/test.svg`]));
    await assert.rejects(db.query("insert into storage.objects(bucket_id,name) values ('tn-post-images',$1)",[`${stranger}/test.jpg`]));
    await as('anon');
    assert.equal((await db.query('select * from public.tn_posts')).rows.length, 0);
    await as('authenticated', admin);
    const published = (await db.query("update public.tn_posts set status='published' where id=$1 returning *",[post.id])).rows[0];
    assert.ok(published.published_at);
    await as('anon');
    assert.equal((await db.query('select * from public.tn_posts')).rows.length, 1);
    await as('authenticated', stranger);
    assert.equal((await db.query("update public.tn_posts set title='Hacked' where id=$1 returning id",[post.id])).rows.length, 0);
    await as('authenticated', admin);
    await db.query("update public.tn_posts set status='archived' where id=$1",[post.id]);
    await assert.rejects(db.query('delete from public.tn_posts where id=$1',[post.id]));
    await as('anon');
    assert.equal((await db.query('select * from public.tn_posts')).rows.length, 0);
    await as('authenticated', admin);
    const restored = (await db.query("update public.tn_posts set status='published' where id=$1 returning *",[post.id])).rows[0];
    assert.equal(new Date(restored.published_at).getTime(),new Date(published.published_at).getTime());
    await assert.rejects(db.query("update public.tn_posts set images=array_fill('x'::text,ARRAY[9]) where id=$1",[post.id]));
    await as('anon');
    const another = (await db.query('select public.tn_record_visit($1) as stats',[stranger])).rows[0].stats;
    assert.deepEqual(another, { visitors: 2, today: 2 });
    await as('postgres');
    await db.query("update public.tn_visit_days set visit_date=visit_date-1 where visitor_id=$1",[visitor]);
    await as('anon');
    const nextDay = (await db.query('select public.tn_record_visit($1) as stats',[visitor])).rows[0].stats;
    assert.deepEqual(nextDay,{visitors:2,today:2});
  } finally { await db.close(); }
});
