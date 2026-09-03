-- Seed dataset demonstrating 0-hop / 1-hop / 2-hop retrieval
-- Run after 001_initial.sql: psql $DATABASE_URL -f supabase/seed.sql

-- Example documents (user_id = null for global seed; real ingests set user_id)
insert into documents (title, source, content, metadata) values
('Turbocharger Basics', 'seed:turbocharger', 'A turbocharger compresses intake air using exhaust gases. The compressor increases air density, allowing more fuel to be burned and increasing engine power. The compressed air passes through an intercooler before entering the combustion chamber.', '{"seed": true, "topic": "turbocharger"}'),
('Intercooler Function', 'seed:intercooler', 'An intercooler is a heat exchanger that cools the compressed air from the turbocharger. By reducing air temperature, it increases density and prevents engine knock. Types include air-to-air and air-to-water intercoolers.', '{"seed": true, "topic": "intercooler"}'),
('Combustion Chamber', 'seed:combustion', 'The combustion chamber is where fuel and compressed air mix and ignite. Its design affects efficiency, emissions, and knock resistance. Modern chambers use direct injection and optimized geometry.', '{"seed": true, "topic": "combustion"}')
on conflict do nothing;

-- Chunks (split manually for seed)
insert into chunks (document_id, chunk_index, content, chunk_id, metadata)
select d.id, 0, d.content, 'chk_seed_' || substr(d.id::text, 1, 8), jsonb_build_object('seed', true, 'source', d.source)
from documents d where d.source like 'seed:%'
on conflict do nothing;

-- Entities
insert into entities (name, type, metadata) values
('Turbocharger', 'COMPONENT', '{"seed": true}'),
('Intercooler', 'COMPONENT', '{"seed": true}'),
('Combustion Chamber', 'COMPONENT', '{"seed": true}'),
('Compressed Air', 'CONCEPT', '{"seed": true}')
on conflict do nothing;

-- Relationships (Turbocharger -> Compressed Air -> Intercooler -> Combustion Chamber)
-- 0-hop: query "What does turbocharger do?" matches Turbocharger chunk
-- 1-hop: query "What happens after turbocharger compresses air?" requires Turbocharger --Compressed Air--> Intercooler
-- 2-hop: query "How does turbocharger affect combustion?" requires Turbocharger -> Intercooler -> Combustion Chamber
insert into relationships (source_entity_id, target_entity_id, relation_type)
select s.id, t.id, 'flows_to'
from entities s, entities t
where s.name='Turbocharger' and t.name='Compressed Air'
on conflict do nothing;

insert into relationships (source_entity_id, target_entity_id, relation_type)
select s.id, t.id, 'cooled_by'
from entities s, entities t
where s.name='Compressed Air' and t.name='Intercooler'
on conflict do nothing;

insert into relationships (source_entity_id, target_entity_id, relation_type)
select s.id, t.id, 'feeds'
from entities s, entities t
where s.name='Intercooler' and t.name='Combustion Chamber'
on conflict do nothing;

-- Link chunks to entities
insert into chunk_entities (chunk_id, entity_id)
select c.id, e.id from chunks c, entities e where c.metadata->>'source'='seed:turbocharger' and e.name='Turbocharger'
on conflict do nothing;
insert into chunk_entities (chunk_id, entity_id)
select c.id, e.id from chunks c, entities e where c.metadata->>'source'='seed:intercooler' and e.name='Intercooler'
on conflict do nothing;
insert into chunk_entities (chunk_id, entity_id)
select c.id, e.id from chunks c, entities e where c.metadata->>'source'='seed:combustion' and e.name='Combustion Chamber'
on conflict do nothing;
