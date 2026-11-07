-- Registry of datasets known to the system. One row per dataset.
create table if not exists public.datasets (
    dataset_id  text primary key check (dataset_id ~ '^[a-z0-9][a-z0-9._-]*$'),
    name        text not null,
    source_url  text not null,
    license     text not null,
    created_at  timestamptz not null default now()
);

comment on table public.datasets is 'Registry of datasets; details live in dataset manifests and cards.';
