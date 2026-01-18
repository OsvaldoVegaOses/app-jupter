/**
 * @fileoverview E2E Tests for basic navigation and page loading.
 */

import { test, expect } from '@playwright/test';

test.describe('Basic Navigation', () => {
    test('homepage loads successfully', async ({ page }) => {
        await page.goto('/');

        // Should have the main title
        await expect(page.locator('h1')).toContainText('Dashboard del ciclo cualitativo');
    });

    test('backend status indicator shows connected', async ({ page }) => {
        await page.goto('/');

        // Wait for BackendStatus to load
        await page.waitForTimeout(2000);

        // Should show connected status
        const backendStatus = page.locator('.backend-status');
        await expect(backendStatus).toBeVisible();

        // Should eventually show "Conectado"
        await expect(page.locator('.backend-status__text')).toContainText(/Conectado/i, { timeout: 10000 });
    });

    test('project selector is visible', async ({ page }) => {
        await page.goto('/');

        // Project selector should be visible
        const projectSelector = page.locator('.app__selector select').first();
        await expect(projectSelector).toBeVisible();
    });

    test('stage cards are rendered', async ({ page }) => {
        await page.goto('/');

        // Should have multiple stage cards
        const stageCards = page.locator('.stage-card');
        await expect(stageCards).toHaveCount(9, { timeout: 10000 }); // 9 stages
    });

    test('system health dashboard exists', async ({ page }) => {
        await page.goto('/');

        // Health dashboard should be present (collapsed by default)
        const healthDashboard = page.locator('.health-dashboard');
        await expect(healthDashboard).toBeVisible();

        // Header should say "Estado del Sistema"
        await expect(page.locator('.health-dashboard__title h3')).toContainText('Estado del Sistema');
    });
});

test.describe('Ingestion Panel', () => {
    test('ingestion panel is accessible', async ({ page }) => {
        await page.goto('/');

        // Click on Stage 2 - Ingesta
        await page.locator('.stage-card').filter({ hasText: 'Ingesta' }).click();

        // Ingestion panel should appear or page should respond
        await page.waitForTimeout(500);
    });
});
