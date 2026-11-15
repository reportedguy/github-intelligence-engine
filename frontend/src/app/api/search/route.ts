import { NextRequest, NextResponse } from 'next/server';
import { executeSearch } from '@/lib/db';
import { SearchFilters, SearchMode } from '@/types/repo';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    const query = searchParams.get('q') || searchParams.get('query') || '';
    const domain = searchParams.get('domain') || 'All';
    const archetype = searchParams.get('archetype') || 'All';
    const language = searchParams.get('language') || 'All';
    const minStarsRaw = searchParams.get('min_stars') || '2000';
    const modeRaw = searchParams.get('mode') || 'semantic';

    const min_stars = Math.max(0, parseInt(minStarsRaw, 10) || 2000);
    const mode: SearchMode = modeRaw === 'keyword' ? 'keyword' : 'semantic';

    const filters: SearchFilters = {
      query,
      domain,
      archetype,
      language,
      min_stars,
      mode,
    };

    const response = await executeSearch(filters);
    return NextResponse.json(response, { status: 200 });
  } catch (error: any) {
    console.error('Search API Route GET Error:', error);
    return NextResponse.json(
      {
        error: 'Failed to execute repository intelligence search',
        message: error?.message || 'Internal Server Error',
        results: [],
        total: 0,
        latency_ms: 0,
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));

    const query = typeof body.query === 'string' ? body.query : '';
    const domain = typeof body.domain === 'string' ? body.domain : 'All';
    const archetype = typeof body.archetype === 'string' ? body.archetype : 'All';
    const language = typeof body.language === 'string' ? body.language : 'All';
    const min_stars = Math.max(0, Number(body.min_stars) || 2000);
    const mode: SearchMode = body.mode === 'keyword' ? 'keyword' : 'semantic';

    const filters: SearchFilters = {
      query,
      domain,
      archetype,
      language,
      min_stars,
      mode,
    };

    const response = await executeSearch(filters);
    return NextResponse.json(response, { status: 200 });
  } catch (error: any) {
    console.error('Search API Route POST Error:', error);
    return NextResponse.json(
      {
        error: 'Failed to execute repository intelligence search',
        message: error?.message || 'Internal Server Error',
        results: [],
        total: 0,
        latency_ms: 0,
      },
      { status: 500 }
    );
  }
}
