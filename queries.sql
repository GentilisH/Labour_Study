-- Each query is executable in SQLite; replace the survey label for a new round.
SELECT * FROM v_hukou_summary WHERE survey_id='pilot-2026';

-- Multiple-choice incidence: option 9 means 'none', so it is excluded here.
SELECT c.hukou,m.option_code,count(m.selected) AS n_observed,
       sum(m.selected) AS experienced,round(100.0*avg(m.selected),1) AS percent
FROM v_current c JOIN multi_answer m USING(revision_id)
WHERE c.survey_id='pilot-2026' AND c.hukou IN(1,2) AND m.question=21 AND m.option_code<=8
GROUP BY c.hukou,m.option_code ORDER BY m.option_code,c.hukou;

-- Observed migration classification is distinct from the requested main classification.
SELECT migration_observed,migration_main,count(*) AS n,
       sum(any_violation) AS experienced,avg(any_violation) AS rate
FROM v_current WHERE survey_id='pilot-2026'
GROUP BY migration_observed,migration_main;

-- Internal comparison among non-agricultural respondents.
SELECT CASE WHEN age_code<=3 THEN 'age_le_30' ELSE 'age_ge_31' END AS age_group,
       count(*) AS n,sum(any_violation) AS experienced,avg(any_violation) AS rate
FROM v_current WHERE survey_id='pilot-2026' AND hukou=2 AND age_code IS NOT NULL
GROUP BY age_group;

-- Inspect revision history; never overwrite original answers.
SELECT r.survey_id,r.source_record_id,v.revision_no,v.is_current,b.imported_at,
       v.answer_sha256,v.coding_sha256
FROM response r JOIN response_revision v USING(response_id)
JOIN import_batch b USING(batch_id) ORDER BY r.response_id,v.revision_no;

-- Reconstruct the exact revisions used in a saved analysis.
SELECT a.run_id,a.snapshot_sha256,count(m.revision_id) AS included_responses
FROM analysis_run a JOIN analysis_member m USING(run_id)
GROUP BY a.run_id,a.snapshot_sha256;
