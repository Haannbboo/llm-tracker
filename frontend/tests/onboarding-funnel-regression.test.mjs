import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const dashboardSrc = readFileSync(join(here, '..', 'src', 'pages', 'DashboardPage.tsx'), 'utf8');
const zhSrc = readFileSync(join(here, '..', 'src', 'i18n', 'zh.ts'), 'utf8');

// Use i18n t() calls as anchors to avoid matching test file's own text.
// These patterns only appear in DashboardPage.tsx JSX, not in the test.
const step1T = "{t('Step 1";
const step2T = "{t('Step 2";
const step3T = "{t('Step 3";

function sectionBetween(src, startMarker, endMarker) {
  const si = src.indexOf(startMarker);
  assert.ok(si !== -1, `Start marker not found: ${startMarker}`);
  const ei = src.indexOf(endMarker, si + startMarker.length);
  assert.ok(ei !== -1, `End marker not found: ${endMarker}`);
  return src.substring(si, ei);
}

function sectionAfter(src, marker) {
  const i = src.indexOf(marker);
  assert.ok(i !== -1, `Marker not found: ${marker}`);
  return src.substring(i);
}

describe('onboarding 3-step funnel', () => {
  it('shows three numbered steps in the onboarding section', () => {
    assert.ok(dashboardSrc.includes(step1T), 'Expected Step 1 t() call in onboarding');
    assert.ok(dashboardSrc.includes(step2T), 'Expected Step 2 t() call in onboarding');
    assert.ok(dashboardSrc.includes(step3T), 'Expected Step 3 t() call in onboarding');
  });

  it('Step 1 is bootstrap (not agent command rows)', () => {
    const area = sectionBetween(dashboardSrc, step1T, step2T);
    assert.ok(
      area.toLowerCase().includes('bootstrap'),
      'Step 1 should reference bootstrap as the primary onboarding action'
    );
    assert.ok(
      !area.includes('llm-tracker claude') && !area.includes('llm-tracker codex') && !area.includes('llm-tracker gemini'),
      'Step 1 should not include agent test command rows — that is Step 2'
    );
  });

  it('Step 1 shows llm-tracker bootstrap as the primary command', () => {
    const area = sectionBetween(dashboardSrc, step1T, step2T);
    assert.ok(
      area.includes('llm-tracker bootstrap'),
      'Step 1 should show "llm-tracker bootstrap" as the primary command to copy'
    );
  });

  it('Step 1 bootstrap command is copyable via CopyButton', () => {
    const area = sectionBetween(dashboardSrc, step1T, step2T);
    assert.ok(
      area.includes('CopyButton'),
      'Step 1 bootstrap command should have a CopyButton for easy copying'
    );
  });

  it('Step 2 is run a test command (existing agent rows)', () => {
    const area = sectionBetween(dashboardSrc, step2T, step3T);
    assert.ok(
      area.toLowerCase().includes('test command') || area.includes('llm-tracker claude'),
      'Step 2 should reference test commands or show agent command rows'
    );
  });

  it('Step 3 waits for event automatically', () => {
    const area = sectionAfter(dashboardSrc, step3T);
    assert.ok(
      area.includes('checks automatically') || area.includes('Waiting for your first event'),
      'Step 3 should reference automatic checking or waiting for the first event'
    );
  });

  it('Chinese translations include 3-step funnel strings', () => {
    // Step 1 Chinese
    assert.ok(
      zhSrc.includes('步骤 1') || zhSrc.includes('Step 1'),
      'zh.ts should have a translation for Step 1'
    );
    // Step 3 Chinese
    assert.ok(
      zhSrc.includes('步骤 3') || zhSrc.includes('Step 3'),
      'zh.ts should have a translation for Step 3'
    );
    // Bootstrap in translations
    assert.ok(
      zhSrc.includes('bootstrap'),
      'zh.ts should include bootstrap in the onboarding translations'
    );
  });
});
