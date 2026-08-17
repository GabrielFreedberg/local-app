create extension if not exists pgcrypto;

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  account_type text not null check (account_type in ('user', 'company')),
  email text not null,
  phone_number text,
  zip_code text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.user_profiles (
  id uuid primary key references public.profiles(id) on delete cascade,
  display_name text,
  alert_channel_email boolean not null default true,
  alert_channel_sms boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.company_profiles (
  id uuid primary key references public.profiles(id) on delete cascade,
  company_name text not null,
  contact_name text,
  status text not null default 'active' check (status in ('active', 'inactive', 'pending_review')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.alert_interests (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(id) on delete cascade,
  label text not null,
  normalized_label text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, normalized_label)
);

create table if not exists public.deals (
  id uuid primary key default gen_random_uuid(),
  deal_type text not null check (deal_type in ('grocery', 'company')),
  company_id uuid references public.company_profiles(id) on delete set null,
  source_store_name text,
  source_store_id text,
  title text not null,
  description text not null,
  category text,
  sale_price numeric(10, 2),
  regular_price numeric(10, 2),
  unit text,
  zip_code text not null,
  address text,
  status text not null default 'active' check (status in ('draft', 'active', 'expired', 'archived')),
  starts_at timestamptz,
  ends_at timestamptz,
  image_url text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.user_profiles(id) on delete cascade,
  deal_id uuid not null references public.deals(id) on delete cascade,
  channel text not null check (channel in ('email', 'sms')),
  status text not null check (status in ('queued', 'sent', 'failed')),
  subject text,
  message text not null,
  matched_interest text,
  error_message text,
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  unique (user_id, deal_id, channel, matched_interest)
);

create index if not exists idx_profiles_account_type on public.profiles(account_type);
create index if not exists idx_profiles_zip_code on public.profiles(zip_code);
create index if not exists idx_alert_interests_user_id on public.alert_interests(user_id);
create index if not exists idx_alert_interests_normalized_label on public.alert_interests(normalized_label);
create index if not exists idx_deals_zip_status on public.deals(zip_code, status);
create index if not exists idx_deals_type_status on public.deals(deal_type, status);
create index if not exists idx_notifications_user_created_at on public.notifications(user_id, created_at desc);

drop trigger if exists trg_profiles_touch_updated_at on public.profiles;
create trigger trg_profiles_touch_updated_at
before update on public.profiles
for each row
execute function public.touch_updated_at();

drop trigger if exists trg_user_profiles_touch_updated_at on public.user_profiles;
create trigger trg_user_profiles_touch_updated_at
before update on public.user_profiles
for each row
execute function public.touch_updated_at();

drop trigger if exists trg_company_profiles_touch_updated_at on public.company_profiles;
create trigger trg_company_profiles_touch_updated_at
before update on public.company_profiles
for each row
execute function public.touch_updated_at();

drop trigger if exists trg_alert_interests_touch_updated_at on public.alert_interests;
create trigger trg_alert_interests_touch_updated_at
before update on public.alert_interests
for each row
execute function public.touch_updated_at();

drop trigger if exists trg_deals_touch_updated_at on public.deals;
create trigger trg_deals_touch_updated_at
before update on public.deals
for each row
execute function public.touch_updated_at();

create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  meta jsonb := coalesce(new.raw_user_meta_data, '{}'::jsonb);
  requested_role text := coalesce(meta->>'account_type', 'user');
  normalized_role text := case
    when requested_role = 'company' then 'company'
    else 'user'
  end;
begin
  insert into public.profiles (id, account_type, email, phone_number, zip_code)
  values (
    new.id,
    normalized_role,
    coalesce(new.email, ''),
    meta->>'phone_number',
    coalesce(meta->>'zip_code', '')
  );

  if normalized_role = 'company' then
    insert into public.company_profiles (id, company_name, contact_name)
    values (
      new.id,
      coalesce(nullif(meta->>'company_name', ''), split_part(coalesce(new.email, 'company'), '@', 1)),
      meta->>'contact_name'
    );
  else
    insert into public.user_profiles (id, display_name)
    values (
      new.id,
      meta->>'display_name'
    );
  end if;

  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row
execute function public.handle_new_auth_user();
