create table public.xiang_pairs (
    code text primary key check (code ~ '^([0-9]{6}|[0-9]{6})$'),
    host_key uuid not null,
    guest_key uuid,
    offer text not null check (length(offer) between 1 and 8192),
    answer text check (length(answer) between 1 and 8192),
    expires_at timestamptz not null default (now() + interval '5 minutes')
);

alter table public.xiang_pairs enable row level security;
revoke all on public.xiang_pairs from public, anon, authenticated;
grant select, insert, update, delete on public.xiang_pairs to service_role;

create function public.xiang_create_pair(p_code text, p_host_key uuid, p_offer text)
returns boolean language plpgsql security invoker set search_path = '' as $$
begin
    perform pg_advisory_xact_lock(45812012);
    delete from public.xiang_pairs where expires_at <= now();
    if (select count(*) from public.xiang_pairs) >= 60 then
        return false;
    end if;
    insert into public.xiang_pairs(code, host_key, offer)
    values (p_code, p_host_key, p_offer) on conflict do nothing;
    return found;
end;
$$;

revoke all on function public.xiang_create_pair(text, uuid, text) from public, anon, authenticated;
grant execute on function public.xiang_create_pair(text, uuid, text) to service_role;

create table public.xiang_pair_limits (
    source_hash text not null,
    is_offer boolean not null,
    bucket timestamptz not null,
    hits integer not null default 1,
    primary key (source_hash, is_offer, bucket)
);
create index xiang_pair_limits_bucket on public.xiang_pair_limits (bucket);

alter table public.xiang_pair_limits enable row level security;
revoke all on public.xiang_pair_limits from public, anon, authenticated;
grant select, insert, update, delete on public.xiang_pair_limits to service_role;

create function public.xiang_allow_pair_request(p_source text, p_offer boolean)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare
    limit_per_window integer := case when p_offer then 25 else 100 end;
    window_start timestamptz := pg_catalog.date_trunc('minute', now());
    used integer;
begin
    delete from public.xiang_pair_limits where bucket < window_start - interval '5 minutes';
    insert into public.xiang_pair_limits as limits (source_hash, is_offer, bucket)
    values (pg_catalog.md5(pg_catalog.left(p_source, 128)), p_offer, window_start)
    on conflict (source_hash, is_offer, bucket) do update
        set hits = limits.hits + 1 where limits.hits < limit_per_window
    returning hits into used;
    return used is not null;
end;
$$;

revoke all on function public.xiang_allow_pair_request(text, boolean) from public, anon, authenticated;
grant execute on function public.xiang_allow_pair_request(text, boolean) to service_role;
