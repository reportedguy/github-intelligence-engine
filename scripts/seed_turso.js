const { createClient } = require('../frontend/node_modules/@libsql/client');
const fs = require('fs');
const path = require('path');

const TURSO_URL = process.env.TURSO_DATABASE_URL || 'libsql://github-intelligence-reportedguy.aws-ap-south-1.turso.io';
const TURSO_AUTH_TOKEN = process.env.TURSO_AUTH_TOKEN || '';

async function main() {
  const client = createClient({
    url: TURSO_URL,
    authToken: TURSO_AUTH_TOKEN,
  });

  // Read mockData.ts and parse the array
  const mockDataContent = fs.readFileSync(
    path.join(__dirname, '..', 'frontend', 'src', 'lib', 'mockData.ts'),
    'utf8'
  );

  // Quick evaluation of mock data records
  // We can extract JSON objects or import them
  const jsCode = mockDataContent
    .replace("import { Repository } from '@/types/repo';", '')
    .replace('export const MOCK_REPOSITORIES: Repository[] =', 'module.exports =');
  
  const tempFile = path.join(__dirname, 'temp_mock.js');
  fs.writeFileSync(tempFile, jsCode);
  const repos = require(tempFile);
  fs.unlinkSync(tempFile);

  console.log(`Seeding ${repos.length} curated repositories to Turso...`);

  const insertSql = `
    INSERT INTO repositories (
      id, full_name, name, owner, url, homepage, description,
      stars_count, forks_count, open_issues_count, primary_language,
      license, is_archived, created_at, pushed_at,
      macro_domain, sub_domain, archetype, problem_solved,
      use_cases, primary_ecosystem, target_audience,
      confidence_score, is_enriched, last_synced_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(id) DO UPDATE SET
      stars_count = excluded.stars_count,
      forks_count = excluded.forks_count,
      open_issues_count = excluded.open_issues_count,
      pushed_at = excluded.pushed_at,
      macro_domain = excluded.macro_domain,
      sub_domain = excluded.sub_domain,
      archetype = excluded.archetype,
      problem_solved = excluded.problem_solved,
      use_cases = excluded.use_cases,
      primary_ecosystem = excluded.primary_ecosystem,
      target_audience = excluded.target_audience,
      confidence_score = excluded.confidence_score,
      is_enriched = excluded.is_enriched;
  `;

  let count = 0;
  for (const r of repos) {
    const args = [
      r.id,
      r.full_name,
      r.name,
      r.owner,
      r.url,
      r.homepage || '',
      r.description || '',
      r.stars_count || 0,
      r.forks_count || 0,
      r.open_issues_count || 0,
      r.primary_language || 'Unknown',
      r.license || 'None',
      r.is_archived ? 1 : 0,
      r.created_at || new Date().toISOString(),
      r.pushed_at || new Date().toISOString(),
      r.macro_domain,
      r.sub_domain,
      r.archetype,
      r.problem_solved,
      JSON.stringify(r.use_cases || []),
      r.primary_ecosystem || '',
      JSON.stringify(r.target_audience || []),
      r.confidence_score || 100,
      r.is_enriched ? 1 : 0,
    ];

    await client.execute({ sql: insertSql, args });
    count++;
    process.stdout.write(`\rUpserted: ${count}/${repos.length} (${r.full_name})`);
  }

  console.log('\nSeed completed successfully!');

  const rowCount = await client.execute('SELECT COUNT(*) AS total FROM repositories');
  console.log(`Total rows in Turso repositories table:`, rowCount.rows[0].total);
}

main().catch(console.error);
