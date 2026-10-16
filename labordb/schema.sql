PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
INSERT OR IGNORE INTO schema_version VALUES(1, strftime('%Y-%m-%dT%H:%M:%SZ','now'));
CREATE TABLE IF NOT EXISTS question_dictionary(
 questionnaire_version TEXT NOT NULL, field TEXT NOT NULL, label TEXT NOT NULL,
 PRIMARY KEY(questionnaire_version,field));
CREATE TABLE IF NOT EXISTS option_dictionary(
 questionnaire_version TEXT NOT NULL, field TEXT NOT NULL, code INTEGER NOT NULL, label TEXT NOT NULL,
 PRIMARY KEY(questionnaire_version,field,code),
 FOREIGN KEY(questionnaire_version,field) REFERENCES question_dictionary);
CREATE TABLE IF NOT EXISTS survey(
 survey_id TEXT PRIMARY KEY, questionnaire_version TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS import_batch(
 batch_id INTEGER PRIMARY KEY, survey_id TEXT NOT NULL REFERENCES survey,
 file_sha256 TEXT NOT NULL, imported_at TEXT NOT NULL, code_version TEXT NOT NULL,
 coding_sha256 TEXT NOT NULL, input_rows INTEGER NOT NULL,
 UNIQUE(survey_id,file_sha256,coding_sha256));
CREATE TABLE IF NOT EXISTS response(
 response_id INTEGER PRIMARY KEY, survey_id TEXT NOT NULL REFERENCES survey,
 source_record_id TEXT NOT NULL, UNIQUE(survey_id,source_record_id));
CREATE TABLE IF NOT EXISTS response_revision(
 revision_id INTEGER PRIMARY KEY, response_id INTEGER NOT NULL REFERENCES response,
 batch_id INTEGER NOT NULL REFERENCES import_batch, revision_no INTEGER NOT NULL,
 is_current INTEGER NOT NULL CHECK(is_current IN(0,1)),
 answer_sha256 TEXT NOT NULL, coding_sha256 TEXT NOT NULL, raw_json TEXT NOT NULL,
 UNIQUE(response_id,revision_no));
CREATE UNIQUE INDEX IF NOT EXISTS one_current_revision ON response_revision(response_id) WHERE is_current=1;
CREATE TABLE IF NOT EXISTS derived(
 revision_id INTEGER PRIMARY KEY REFERENCES response_revision,
 age_code INTEGER CHECK(age_code BETWEEN 1 AND 7),
 hukou INTEGER CHECK(hukou IN(1,2,3)),
 employment_code INTEGER CHECK(employment_code BETWEEN 1 AND 6),
 income_code INTEGER CHECK(income_code BETWEEN 1 AND 8),
 migration_observed TEXT NOT NULL CHECK(migration_observed IN('local','nonlocal','unknown')),
 migration_main TEXT NOT NULL CHECK(migration_main IN('local','nonlocal')),
 industry TEXT NOT NULL, current_status TEXT NOT NULL,
 days_low REAL, days_high REAL, hours_low REAL, hours_high REAL,
 weekly_hours REAL, q21_conflict INTEGER NOT NULL CHECK(q21_conflict IN(0,1)),
 any_violation INTEGER CHECK(any_violation IN(0,1)), violation_count INTEGER,
 knowledge_count INTEGER CHECK(knowledge_count BETWEEN 0 AND 6));
CREATE TABLE IF NOT EXISTS answer(
 revision_id INTEGER NOT NULL REFERENCES response_revision,
 field TEXT NOT NULL, value TEXT, PRIMARY KEY(revision_id,field));
CREATE TABLE IF NOT EXISTS multi_answer(
 revision_id INTEGER NOT NULL REFERENCES response_revision,
 question INTEGER NOT NULL CHECK(question IN(21,23,24)), option_code INTEGER NOT NULL,
 selected INTEGER CHECK(selected IN(0,1)), PRIMARY KEY(revision_id,question,option_code));
CREATE TABLE IF NOT EXISTS quality_issue(
 issue_id INTEGER PRIMARY KEY, revision_id INTEGER NOT NULL REFERENCES response_revision,
 field TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_run(
 run_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, code_version TEXT NOT NULL,
 python_version TEXT NOT NULL, sqlite_version TEXT NOT NULL,
 snapshot_sha256 TEXT NOT NULL, parameters_json TEXT NOT NULL, results_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS analysis_member(
 run_id TEXT NOT NULL REFERENCES analysis_run,
 revision_id INTEGER NOT NULL REFERENCES response_revision,
 PRIMARY KEY(run_id,revision_id));
CREATE VIEW IF NOT EXISTS v_current AS
 SELECT r.survey_id,r.source_record_id,rr.response_id,rr.revision_no,rr.raw_json,d.*
 FROM response r JOIN response_revision rr USING(response_id)
 JOIN derived d USING(revision_id) WHERE rr.is_current=1;
CREATE VIEW IF NOT EXISTS v_hukou_summary AS
 SELECT survey_id,hukou,count(*) AS n,count(any_violation) AS n_observed,
 sum(any_violation) AS experienced,avg(any_violation) AS experience_rate,
 avg(violation_count) AS mean_type_count FROM v_current GROUP BY survey_id,hukou;
