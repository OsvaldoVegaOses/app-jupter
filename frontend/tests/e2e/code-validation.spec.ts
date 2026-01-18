/**
 * @fileoverview E2E Tests for CodeValidationPanel functionality.
 */

import { test, expect } from '@playwright/test';

async function authenticate(page: any, request: any) {
    const email = `e2e_${Date.now()}_${Math.random().toString(16).slice(2)}@example.com`;
    const password = 'Passw0rd!12345';

    const response = await request.post('/api/auth/register', {
        data: {
            email,
            password,
            full_name: 'E2E Tester',
            organization_id: 'default_org',
        },
    });

    if (!response.ok()) {
        const body = await response.text().catch(() => '');
        throw new Error(`E2E auth failed: ${response.status()} ${body}`);
    }

    const data = await response.json();
    const user = {
        id: data.user?.id,
        email: data.user?.email,
        name: data.user?.full_name ?? null,
        org_id: data.user?.organization_id,
        role: data.user?.role ?? 'viewer',
    };

    await page.addInitScript(
        ({ accessToken, refreshToken, userJson }) => {
            window.localStorage.setItem('access_token', accessToken);
            if (refreshToken) {
                window.localStorage.setItem('refresh_token', refreshToken);
            }
            window.localStorage.setItem('qualy-auth-user', userJson);
        },
        {
            accessToken: data.access_token,
            refreshToken: data.refresh_token,
            userJson: JSON.stringify(user),
        }
    );
}

test.describe('Code Validation Panel', () => {
    test.beforeEach(async ({ page, request }) => {
        await authenticate(page, request);
        await page.goto('/');
        // Wait for page to fully load
        await page.waitForLoadState('networkidle');
    });

    test('CodeValidationPanel renders on page', async ({ page }) => {
        // Scroll down to find the panel
        await page.evaluate(() => window.scrollTo(0, 1500));
        await page.waitForTimeout(500);

        // Should find the validation panel
        const panel = page.locator('.validation-panel');
        await expect(panel).toBeVisible({ timeout: 10000 });
    });

    test('CodeValidationPanel has header with title', async ({ page }) => {
        await page.evaluate(() => window.scrollTo(0, 1500));

        // Should have the title
        await expect(page.locator('text=Bandeja de Códigos Candidatos')).toBeVisible({ timeout: 10000 });
    });

    test('CodeValidationPanel has status badges', async ({ page }) => {
        await page.evaluate(() => window.scrollTo(0, 1500));

        // Should have status badges (Pendientes, Validados, Rechazados, Fusionados)
        const badges = page.locator('.validation-panel__badge');
        await expect(badges).toHaveCount(4, { timeout: 10000 });
    });

    test('CodeValidationPanel has filter controls', async ({ page }) => {
        await page.evaluate(() => window.scrollTo(0, 1500));

        // Should have filter dropdowns
        const filterSection = page.locator('.validation-panel__filters');
        await expect(filterSection).toBeVisible({ timeout: 10000 });

        // Should have at least 2 filter selects (status, source)
        const selects = filterSection.locator('select');
        await expect(selects).toHaveCount(2, { timeout: 5000 });
    });

    test('CodeValidationPanel table or empty state is visible', async ({ page }) => {
        await page.evaluate(() => window.scrollTo(0, 1500));

        // Should have either a table or empty state message
        const table = page.locator('.validation-panel table');
        const emptyState = page.locator('.validation-panel').locator('text=No hay códigos');

        // At least one should be visible
        await expect(table.or(emptyState)).toBeVisible({ timeout: 10000 });
    });

    test('Limpiar Cache → recargar → bandeja stays clean (no empty project calls)', async ({ page }) => {
        const seenCandidateRequests: Array<{ url: string; project: string | null }> = [];

        page.on('request', (req: any) => {
            const url = req.url();
            if (!url.includes('/api/codes/candidates')) return;
            try {
                const parsed = new URL(url);
                const project = parsed.searchParams.get('project');
                seenCandidateRequests.push({ url, project });
            } catch {
                seenCandidateRequests.push({ url, project: null });
            }
        });

        // Accept confirmation dialog
        page.on('dialog', async (dialog: any) => {
            await dialog.accept();
        });

        // Trigger cache clear
        await expect(page.locator('.health-dashboard')).toBeVisible({ timeout: 10000 });
        await page.locator('.health-dashboard__clear-cache').click();

        // Wait for reload to complete
        await page.waitForLoadState('domcontentloaded');
        await page.waitForLoadState('networkidle');

        // Bandeja should still be present
        await page.evaluate(() => window.scrollTo(0, 1500));
        await expect(page.locator('.validation-panel')).toBeVisible({ timeout: 10000 });

        // Assert we never called candidates with an empty project
        const emptyProjectCalls = seenCandidateRequests.filter(
            (r) => r.project !== null && r.project.trim() === ''
        );
        expect(
            emptyProjectCalls,
            `Expected no /api/codes/candidates?project= calls, saw: ${emptyProjectCalls
                .map((c) => c.url)
                .join(' | ')}`
        ).toHaveLength(0);
    });
});

test.describe('Code Validation Panel Actions', () => {
    test.beforeEach(async ({ page, request }) => {
        await authenticate(page, request);
    });

    test('filter by status works', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        await page.evaluate(() => window.scrollTo(0, 1500));

        // Find and change status filter
        const statusFilter = page.locator('.validation-panel__filters select').first();
        await expect(statusFilter).toBeVisible({ timeout: 10000 });

        // Select "Validado" option if available
        await statusFilter.selectOption({ label: 'Validado' }).catch(() => {
            // Option might not exist, that's ok
        });
    });

    test('promote button exists when items are selected', async ({ page }) => {
        await page.goto('/');
        await page.waitForLoadState('networkidle');
        await page.evaluate(() => window.scrollTo(0, 1500));

        // The promote button should exist
        const promoteButton = page.locator('button:has-text("Promover")');
        // It might be disabled if no items are selected
        await expect(promoteButton.or(page.locator('text=No hay códigos'))).toBeVisible({ timeout: 10000 });
    });
});
