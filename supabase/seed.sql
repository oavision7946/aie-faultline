-- Seed data loaded after migrations on every database reset.
-- Public datasets only; licenses are confirmed during dataset review.
insert into public.datasets (dataset_id, name, source_url, license) values
    ('loghub-2k', 'Loghub 2k-line samples', 'https://github.com/logpai/loghub', 'pending-review'),
    ('hdfs-v1', 'HDFS_v1', 'https://github.com/logpai/loghub', 'pending-review')
on conflict (dataset_id) do nothing;
