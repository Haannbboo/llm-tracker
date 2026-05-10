import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const appSrc = readFileSync(join(here, '..', 'src', 'App.tsx'), 'utf8');
const insightCardsSrc = readFileSync(join(here, '..', 'src', 'InsightCards.tsx'), 'utf8');
const zhSrc = readFileSync(join(here, '..', 'src', 'i18n', 'zh.ts'), 'utf8');

describe('InsightCards regression', () => {
  it('InsightCards is imported and used in App.tsx', () => {
    assert.ok(
      appSrc.includes("import { InsightCards } from './InsightCards'"),
      'App.tsx should import InsightCards'
    );
    assert.ok(
      appSrc.includes("<InsightCards summary={summary} dailyUsage={dailyUsage} />"),
      'App.tsx should use InsightCards component'
    );
  });

  it('InsightCards.tsx uses correct i18n keys', () => {
    const expectedKeys = [
      'Top Cost Driver',
      'Latency Watch',
      'Usage Trend',
      'Reliability Watch',
      'Trending Up',
      'Trending Down',
      'change',
      'failed requests',
      'Check logs for details'
    ];

    for (const key of expectedKeys) {
      assert.ok(
        insightCardsSrc.includes(`t('${key}')`),
        `InsightCards.tsx should use i18n key: ${key}`
      );
    }
  });

  it('zh.ts contains translations for InsightCards keys', () => {
    const expectedKeys = [
      'Top Cost Driver',
      'Latency Watch',
      'Usage Trend',
      'Reliability Watch',
      'Trending Up',
      'Trending Down',
      'change',
      'failed requests',
      'Check logs for details'
    ];

    for (const key of expectedKeys) {
      assert.ok(
        zhSrc.includes(`'${key}':`),
        `zh.ts should have translation for: ${key}`
      );
    }
  });

  it('InsightCards handles data correctly and renders cards', () => {
    // Basic structural check of the component
    assert.ok(
      insightCardsSrc.includes('export function InsightCards'),
      'InsightCards should export a function component'
    );
    assert.ok(
      insightCardsSrc.includes('className="insights-grid"'),
      'InsightCards should render an insights-grid container'
    );
    assert.ok(
      insightCardsSrc.includes('className={`insight-card'),
      'InsightCards should render individual insight-cards'
    );
  });

  it('InsightCards depends on lang and normalizes trend', () => {
    assert.ok(
      insightCardsSrc.includes('const { lang } = useLang()'),
      'InsightCards should use lang from useLang'
    );
    assert.ok(
      insightCardsSrc.includes('}, [summary, dailyUsage, lang])'),
      'InsightCards useMemo should depend on lang'
    );
    assert.ok(
      insightCardsSrc.includes('const firstHalfAvg = firstHalf / firstHalfCount'),
      'InsightCards should normalize trend by bucket count'
    );
    assert.ok(
      insightCardsSrc.includes('const secondHalfAvg = secondHalf / secondHalfCount'),
      'InsightCards should normalize trend by bucket count'
    );
  });
});
