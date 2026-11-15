const fs = require('fs');
const path = require('path');
const { createClient } = require('../frontend/node_modules/@libsql/client');

const TURSO_URL = process.env.TURSO_DATABASE_URL || 'libsql://github-intelligence-reportedguy.aws-ap-south-1.turso.io';
const TURSO_AUTH_TOKEN = process.env.TURSO_AUTH_TOKEN || '';

async function main() {
  console.log('Connecting to Turso:', TURSO_URL);
  const client = createClient({
    url: TURSO_URL,
    authToken: TURSO_AUTH_TOKEN,
  });

  const schemaPath = path.join(__dirname, '..', 'turso', 'schema.sql');
  const sql = fs.readFileSync(schemaPath, 'utf8');

  // Statements to run
  const statements = [
    `CREATE TABLE IF NOT EXISTS repositories (
      id INTEGER PRIMARY KEY,
      full_name TEXT UNIQUE NOT NULL,
      name TEXT NOT NULL,
      owner TEXT NOT NULL,
      url TEXT NOT NULL,
      homepage TEXT,
      description TEXT,
      stars_count INTEGER NOT NULL,
      forks_count INTEGER NOT NULL,
      open_issues_count INTEGER NOT NULL,
      primary_language TEXT,
      license TEXT,
      is_archived INTEGER DEFAULT 0,
      created_at TEXT,
      pushed_at TEXT,
      macro_domain TEXT NOT NULL,
      sub_domain TEXT NOT NULL,
      archetype TEXT NOT NULL,
      problem_solved TEXT NOT NULL,
      use_cases TEXT NOT NULL,
      primary_ecosystem TEXT NOT NULL,
      target_audience TEXT NOT NULL,
      confidence_score INTEGER DEFAULT 100,
      is_enriched INTEGER DEFAULT 0,
      embedding F32_BLOB(384),
      last_synced_at TEXT DEFAULT (datetime('now'))
    );`,
    `CREATE INDEX IF NOT EXISTS idx_repos_vector ON repositories(libsql_vector_idx(embedding));`,
    `CREATE INDEX IF NOT EXISTS idx_repos_stars ON repositories(stars_count DESC);`,
    `CREATE INDEX IF NOT EXISTS idx_repos_domain ON repositories(macro_domain);`,
    `CREATE INDEX IF NOT EXISTS idx_repos_archetype ON repositories(archetype);`,
    `CREATE INDEX IF NOT EXISTS idx_repos_language ON repositories(primary_language);`,
    `CREATE INDEX IF NOT EXISTS idx_repos_enriched ON repositories(is_enriched);`,
    `CREATE INDEX IF NOT EXISTS idx_repos_pushed_at ON repositories(pushed_at DESC);`,
    `CREATE INDEX IF NOT EXISTS idx_repos_domain_stars ON repositories(macro_domain, stars_count DESC);`
  ];

  for (const stmt of statements) {
    try {
      console.log('Executing:', stmt.split('\n')[0]);
      await client.execute(stmt);
      console.log('✓ Success');
    } catch (err) {
      console.error('Error executing statement:', err.message);
    }
  }

  // Verify tables
  const tables = await client.execute("SELECT name FROM sqlite_master WHERE type='table'");
  console.log('Created tables:', tables.rows);

  const indexes = await client.execute("SELECT name FROM sqlite_master WHERE type='index'");
  console.log('Created indexes:', indexes.rows.map(r => r.name));
}

main().catch(console.error);
