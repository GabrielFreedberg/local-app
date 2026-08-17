alter table public.profiles enable row level security;
alter table public.user_profiles enable row level security;
alter table public.company_profiles enable row level security;
alter table public.alert_interests enable row level security;
alter table public.deals enable row level security;
alter table public.notifications enable row level security;

create or replace function public.current_account_type()
returns text
language sql
stable
as $$
  select account_type
  from public.profiles
  where id = auth.uid()
$$;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
on public.profiles
for select
using (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
on public.profiles
for update
using (auth.uid() = id)
with check (auth.uid() = id);

drop policy if exists "user_profiles_select_own" on public.user_profiles;
create policy "user_profiles_select_own"
on public.user_profiles
for select
using (auth.uid() = id);

drop policy if exists "user_profiles_update_own" on public.user_profiles;
create policy "user_profiles_update_own"
on public.user_profiles
for update
using (auth.uid() = id and public.current_account_type() = 'user')
with check (auth.uid() = id and public.current_account_type() = 'user');

drop policy if exists "company_profiles_select_own" on public.company_profiles;
create policy "company_profiles_select_own"
on public.company_profiles
for select
using (auth.uid() = id);

drop policy if exists "company_profiles_update_own" on public.company_profiles;
create policy "company_profiles_update_own"
on public.company_profiles
for update
using (auth.uid() = id and public.current_account_type() = 'company')
with check (auth.uid() = id and public.current_account_type() = 'company');

drop policy if exists "alert_interests_select_own" on public.alert_interests;
create policy "alert_interests_select_own"
on public.alert_interests
for select
using (auth.uid() = user_id and public.current_account_type() = 'user');

drop policy if exists "alert_interests_insert_own" on public.alert_interests;
create policy "alert_interests_insert_own"
on public.alert_interests
for insert
with check (auth.uid() = user_id and public.current_account_type() = 'user');

drop policy if exists "alert_interests_update_own" on public.alert_interests;
create policy "alert_interests_update_own"
on public.alert_interests
for update
using (auth.uid() = user_id and public.current_account_type() = 'user')
with check (auth.uid() = user_id and public.current_account_type() = 'user');

drop policy if exists "alert_interests_delete_own" on public.alert_interests;
create policy "alert_interests_delete_own"
on public.alert_interests
for delete
using (auth.uid() = user_id and public.current_account_type() = 'user');

drop policy if exists "deals_select_active_authenticated" on public.deals;
create policy "deals_select_active_authenticated"
on public.deals
for select
using (auth.role() = 'authenticated' and status = 'active');

drop policy if exists "deals_insert_company_own" on public.deals;
create policy "deals_insert_company_own"
on public.deals
for insert
with check (
  public.current_account_type() = 'company'
  and auth.uid() = company_id
  and deal_type = 'company'
);

drop policy if exists "deals_update_company_own" on public.deals;
create policy "deals_update_company_own"
on public.deals
for update
using (
  public.current_account_type() = 'company'
  and auth.uid() = company_id
)
with check (
  public.current_account_type() = 'company'
  and auth.uid() = company_id
);

drop policy if exists "deals_delete_company_own" on public.deals;
create policy "deals_delete_company_own"
on public.deals
for delete
using (
  public.current_account_type() = 'company'
  and auth.uid() = company_id
);

drop policy if exists "notifications_select_own" on public.notifications;
create policy "notifications_select_own"
on public.notifications
for select
using (auth.uid() = user_id and public.current_account_type() = 'user');
