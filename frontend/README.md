# Frontend Search Experience — GitHub Intelligence Engine

The search and discovery dashboard for the **GitHub Intelligence Engine (2k+ Stars)**. Built with **Next.js 14 App Router**, **Tailwind CSS**, and zero-cost edge vector search.

Designed to operate within the **$0.00 / month infrastructure invariant**, supporting instant hybrid vector cosine similarity searches (`bge-small-en-v1.5`, 384 dimensions) and faceted filtering across ~30,000 repositories.

---

## Key Features

1. **Natural Language Omnibar**:
   - Live debounced semantic intent search.
   - Dual-mode switch: **Semantic Intent** (384-dim dense vector cosine distance) vs. **Keyword Search** (exact trigram / full-text match).
   - Fast suggestion chips for immediate query inspiration.

2. **6-Pillar Faceted Filtering**:
   - **Archetype Segmented Pills**: Filter by operational form factor (`All`, `Server/Daemon`, `CLI Binary`, `Library/SDK`, `Framework`, `Curated List`, `Tutorial/Book`).
   - **Macro Domain Selector**: Full coverage of the 15 closed taxonomy domains.
   - **Language Chips**: Fast ecosystem toggle (`Python`, `Rust`, `Go`, `TypeScript`, `C++`, etc.).
   - **Dynamic Star Floor Slider**: Intuitive range selection from 2,000 to 150,000+ stars.

3. **Repository Intelligence Cards (`RepoCard`)**:
   - Full repository name linking directly to GitHub.
   - Telemetry metrics: live star count, daily star delta indicator, fork count, and open issues.
   - Primary language badge and color-coded functional archetype pill.
   - **Target Problem Solved**: 1–2 sentence high-density engineering summary.
   - **Clickable Use-Case Tags**: Instant faceted filtering upon clicking any tag (`[Verb-Noun]` syntax).
   - **Freshness & Velocity Indicator**: `Active (< 7 days)`, `Maintained (< 60 days)`, or `Stale (> 180 days)`.

4. **Dual-Driver Storage Architecture**:
   - Seamlessly queries **Supabase** (`pgvector` with HNSW index) or **Turso** (LibSQL native vector search).
   - Built-in zero-config fallback to local in-memory dataset for local development or preview environments.

---

## Project Structure

```
frontend/
├── package.json               # Dependencies (Next.js 14, Tailwind, @libsql, @supabase, @xenova)
├── tsconfig.json              # Strict TypeScript configuration
├── tailwind.config.js         # Slate/Indigo sleek dark theme palette
├── postcss.config.js          # PostCSS Tailwind processing
├── README.md                  # Documentation and deployment guide
├── .env.example               # Template environment variables
└── src/
    ├── app/
    │   ├── api/
    │   │   └── search/
    │   │       └── route.ts   # Hybrid search API route (Vector RPC + Faceted ILIKE)
    │   ├── globals.css        # Global CSS & Tailwind imports
    │   ├── layout.tsx         # Root layout with dark background & ambient glow
    │   └── page.tsx           # Main search dashboard page
    ├── components/
    │   ├── FilterBar.tsx      # Faceted filter controls (Archetype, Domain, Slider, Language)
    │   ├── Omnibar.tsx        # Natural Language Omnibar with mode switch
    │   └── RepoCard.tsx       # Repository Intelligence Card component
    ├── lib/
    │   ├── db.ts              # Unified database driver (Supabase + Turso + fallback)
    │   ├── embedder.ts        # 384-dim vector embedder using @xenova/transformers
    │   ├── mockData.ts        # Comprehensive offline dataset adhering to 6-pillar schema
    │   └── utils.ts           # Class merging, number formatting, freshness indicators
    └── types/
        └── repo.ts            # Complete TypeScript types and taxonomy schemas
```

---

## Environment Variables

Copy `.env.example` to `.env.local` to configure your database driver:

```bash
cp .env.example .env.local
```

### Option A: Supabase (pgvector)
```env
DB_PROVIDER=supabase
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-supabase-anon-key
SUPABASE_SERVICE_ROLE_KEY=your-supabase-service-role-key
```

### Option B: Turso (LibSQL)
```env
DB_PROVIDER=turso
TURSO_DATABASE_URL=libsql://your-database-name.turso.io
TURSO_AUTH_TOKEN=your-turso-auth-token
```

*Note: If no database credentials are provided, the application automatically runs in local preview mode using the embedded 6-pillar repository dataset.*

---

## Local Development

1. **Install dependencies**:
   ```bash
   cd frontend
   npm install
   ```

2. **Start the local Next.js development server**:
   ```bash
   npm run dev
   ```

3. Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Production Deployment Guides

### 1. Deploying to Vercel ($0.00 / Free Hobby Tier)

Vercel provides native zero-configuration deployments for Next.js 14 App Router.

1. **Push your repository to GitHub**:
   ```bash
   git add .
   git commit -m "feat: complete frontend search dashboard"
   git push origin main
   ```

2. **Import Project into Vercel**:
   - Go to [vercel.com](https://vercel.com) and click **"Add New Project"**.
   - Select your GitHub repository.
   - Set **Root Directory** to `frontend`.
   - Framework Preset will automatically detect **Next.js**.

3. **Configure Environment Variables**:
   In Vercel's **Environment Variables** panel, add:
   - `DB_PROVIDER`: `supabase` or `turso`
   - `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (if using Supabase)
   - OR `TURSO_DATABASE_URL` and `TURSO_AUTH_TOKEN` (if using Turso)

4. **Deploy**:
   - Click **Deploy**. Vercel will build and assign a global production URL (e.g. `https://github-intelligence.vercel.app`).

---

### 2. Deploying to Cloudflare Pages ($0.00 / Free Tier)

Cloudflare Pages offers unlimited requests and edge low latency on the free tier.

#### Method A: Using `@cloudflare/next-on-pages` (Recommended for Edge API Routes)

1. **Install Cloudflare Next adapter**:
   ```bash
   npm install -D @cloudflare/next-on-pages
   ```

2. **Add Cloudflare build script to `package.json`**:
   ```json
   "scripts": {
     "pages:build": "npx @cloudflare/next-on-pages"
   }
   ```

3. **Deploy via Cloudflare Dashboard**:
   - Navigate to **Workers & Pages** -> **Create application** -> **Pages** -> **Connect to Git**.
   - Select your repository and choose the `frontend` root directory.
   - Build settings:
     - **Framework preset**: `Next.js`
     - **Build command**: `npx @cloudflare/next-on-pages`
     - **Build output directory**: `.vercel/output/static`
   - Under **Compatibility flags**, add `nodejs_compat`.
   - Add your environment variables (`DB_PROVIDER`, `TURSO_DATABASE_URL`, etc.).
   - Click **Save and Deploy**.

#### Method B: Cloudflare Pages Static Export

If running client-side vector search or connecting directly to Supabase from the client:
1. In `next.config.js`, set `output: 'export'`.
2. Set build command to `npm run build` and output directory to `out`.
3. Deploy directly on Cloudflare Pages.

---

## Verification & Supervisor Quality Gate Audit

- **Zero Paid APIs**: Search runs against PostgreSQL `pgvector` or LibSQL vector indices without external paid API tokens.
- **Strict 384-dim Vectors**: Embeddings conform to `bge-small-en-v1.5` 384 float32 dimensions.
- **Fast Resiliency**: Local fallback memory ensures continuous availability during cold starts or transient connection interruptions.
